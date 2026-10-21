"""Doble de prueba del cliente Proxmox.

Permite ejercitar los caminos de fallo de infraestructura sin un clúster real,
como exige la compuerta de calidad de la constitución del proyecto.
"""

from collections import deque
from datetime import datetime, timedelta, timezone
from copy import deepcopy


class FakeClock:
    def __init__(self, current=None):
        self.current = current or datetime(2027, 3, 1, tzinfo=timezone.utc)
        if self.current.tzinfo is None:
            raise ValueError('El reloj debe tener zona horaria')

    def now(self):
        return self.current

    def advance(self, **delta):
        self.current += timedelta(**delta)
        return self.current


class ProxmoxFalla(Exception):
    """Error genérico de infraestructura, equivalente a lo que levanta proxmoxer."""


class ProxmoxAusente(ProxmoxFalla):
    status_code = 404


# Enumeración que acepta `cluster/resources` en Proxmox VE. No incluye "lxc".
TIPOS_RECURSO_VALIDOS = {"vm", "storage", "node", "sdn"}


class FakeProxmoxClient:
    """
    Cliente Proxmox simulado y configurable.

    Knobs principales:
      - ``fallar_create``: si se setea, ``create_lxc`` levanta esa excepción.
      - ``fallar_delete``: si se setea, ``delete_lxc`` levanta esa excepción.
      - ``next_vmid``: valor que devuelve ``get_next_vmid``.
      - ``recursos``: contenido de ``get_cluster_resources`` (VMIDs ya ocupados).

    Registra además lo que se le pidió (``creados``, ``eliminados``, ``detenidos``)
    para poder afirmar que un reintento no duplicó contenedores.
    """

    def __init__(
        self,
        next_vmid: int = 100,
        fallar_create: Exception | None = None,
        fallar_task: Exception | None = None,
        fallar_delete: Exception | None = None,
        fallar_start: Exception | None = None,
        fallar_stop: Exception | None = None,
        fallar_reboot: Exception | None = None,
        fallar_recursos: Exception | None = None,
        recursos: list[dict] | None = None,
        nodos: list[dict] | None = None,
        retraso_resumen: bool = False,
    ):
        self.next_vmid = next_vmid
        self.fallar_create = fallar_create
        # Fallo *dentro* de la tarea de Proxmox: la llamada devuelve el task id
        # sin problemas y el error recién aparece al esperar su resultado.
        self.fallar_task = fallar_task
        self.fallar_delete = fallar_delete
        self.fallar_start = fallar_start
        self.fallar_stop = fallar_stop
        self.fallar_reboot = fallar_reboot
        self.fallar_recursos = fallar_recursos
        # Simula el retraso real de `cluster/resources`: pvestatd lo refresca
        # cada ~10 s, así que durante esa ventana el resumen sigue reportando el
        # estado anterior aunque el contenedor ya haya cambiado.
        self.retraso_resumen = retraso_resumen
        self.recursos = recursos if recursos is not None else []
        self.nodos = nodos if nodos is not None else [
            {"node": "pve1", "status": "online", "cpu": 0.1},
            {"node": "pve2", "status": "online", "cpu": 0.5},
        ]

        # Registro de llamadas
        self.creados: list[dict] = []
        self.eliminados: list[tuple[str, int]] = []
        self.detenidos: list[tuple[str, int]] = []
        self.iniciados: list[tuple[str, int]] = []
        self.reiniciados: list[tuple[str, int]] = []
        self.llamadas_next_vmid = 0
        self.tasks_esperadas: list[tuple] = []

        # Estado simulado de los contenedores: vmid -> estado
        self.estados: dict[int, str] = {}
        self.configuraciones = {}
        self.storages = []
        self.contenidos_storage = {}
        self.tareas = {}
        self.task_polls = []
        self.task_history = []

    def _task(self, node, vmid, action):
        from app.utils.clock import clock
        upid = f'UPID:{node}:task:{action}'
        self.task_history.append({'upid': upid, 'node': node, 'id': str(vmid),
            'type': {'create': 'vzcreate', 'start': 'vzstart', 'stop': 'vzstop', 'reboot': 'vzreboot', 'delete': 'vzdestroy'}[action],
            'starttime': int(clock.now().timestamp())})
        return upid

    def get_node_tasks(self, node, *, vmid, since, tipo):
        return [deepcopy(task) for task in self.task_history if task['node'] == node
                and task['id'] == str(vmid) and task['type'] == tipo and task['starttime'] >= since]

    # --- Nodos ---

    def get_nodes(self) -> list[dict]:
        return self.nodos

    def get_node_status(self, node):
        return next(deepcopy(n) for n in self.nodos if n['node'] == node)

    def get_node_storage(self, node):
        return deepcopy([s for s in self.storages if s.get('node', node) == node])

    def get_storage_status(self, node, storage):
        return next(s for s in self.get_node_storage(node) if s['storage'] == storage)

    def get_storage_content(self, node, storage):
        return deepcopy(self.contenidos_storage.get((node, storage), []))

    def configure_task(self, node, upid, states, effect=None):
        """Estados de polling; el efecto se observa solo al confirmar OK."""
        self.tareas[(node, upid)] = {'states': deque(deepcopy(states)), 'effect': effect}

    def get_task_status(self, node, upid):
        self.task_polls.append((node, upid))
        task = self.tareas.get((node, upid))
        if task is None:
            return {'status': 'stopped', 'exitstatus': 'OK'}
        states = task['states']
        result = states.popleft() if len(states) > 1 else states[0]
        if isinstance(result, Exception):
            raise result
        if result.get('status') == 'stopped' and result.get('exitstatus') == 'OK' and task['effect']:
            task['effect']()
            task['effect'] = None
        return deepcopy(result)

    def get_lxc_config(self, node, vmid):
        if (node, int(vmid)) not in self.configuraciones:
            raise ProxmoxAusente()
        return deepcopy(self.configuraciones[(node, int(vmid))])

    def get_qemu_config(self, node, vmid):
        return self.get_lxc_config(node, vmid)

    def get_available_templates(self, node, storage='local'):
        return deepcopy(self.contenidos_storage.get((node, storage), []))

    def update_lxc_config(self, node, vmid, **config):
        self.configuraciones.setdefault((node, int(vmid)), {}).update(deepcopy(config))

    # --- Contenedores LXC ---

    def create_lxc(self, node: str, **kwargs) -> str:
        if self.fallar_create is not None:
            raise self.fallar_create
        self.creados.append({"node": node, **kwargs})
        vmid = int(kwargs.get("vmid", self.next_vmid))
        self.configuraciones[(node, vmid)] = deepcopy(kwargs)
        storage, size = kwargs['rootfs'].split(':')
        volume = f'{storage}:vm-{vmid}-disk-0'
        self.configuraciones[(node, vmid)]['rootfs'] = f'{volume},size={size}G'
        self.contenidos_storage.setdefault((node, storage), []).append({'volid': volume, 'size': int(size) * 1024**3, 'content': 'rootdir'})
        self.estados[vmid] = "running"
        # Reflejar el contenedor recién creado en los recursos del clúster
        self.recursos.append(
            {
                "type": "lxc",
                "vmid": vmid,
                "name": kwargs.get("hostname"),
                "node": node,
                "status": "running",
                "pool": kwargs.get('pool'),
            }
        )
        return self._task(node, vmid, 'create')

    def esperar_task(self, node, task_id, timeout=None):
        if self.fallar_task is not None:
            raise self.fallar_task
        self.tasks_esperadas.append((node, task_id))

    def _marcar(self, vmid: int, status: str) -> None:
        """Cambia el estado del contenedor en las dos vistas que expone el doble.

        `get_lxc_status` y `cluster/resources` describen el mismo contenedor: si
        el doble las deja divergir, deja pasar justamente el desfase que la
        reconciliación existe para corregir.
        """
        self.estados[vmid] = status
        if self.retraso_resumen:
            return
        for recurso in self.recursos:
            if int(recurso.get("vmid", -1)) == vmid:
                recurso["status"] = status

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        """Estado del contenedor según el nodo que lo hospeda.

        Cae de vuelta a lo que declara el resumen del clúster para los VMIDs que
        una prueba montó ahí directamente: las dos vistas describen el mismo
        contenedor y solo deben diferir cuando la prueba pide expresamente
        simular el retraso del resumen.
        """
        vmid = int(vmid)
        if vmid in self.estados:
            return {"status": self.estados[vmid]}
        for recurso in self.recursos:
            if int(recurso.get("vmid", -1)) == vmid:
                return {"status": recurso.get("status", "stopped")}
        return {"status": "stopped"}

    def start_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_start is not None:
            raise self.fallar_start
        self.iniciados.append((node, int(vmid)))
        self._marcar(int(vmid), "running")
        return self._task(node, vmid, 'start')

    def stop_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_stop is not None:
            raise self.fallar_stop
        self.detenidos.append((node, int(vmid)))
        self._marcar(int(vmid), "stopped")
        return self._task(node, vmid, 'stop')

    def reboot_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_reboot is not None:
            raise self.fallar_reboot
        self.reiniciados.append((node, int(vmid)))
        return self._task(node, vmid, 'reboot')

    def abrir_termproxy(self, node: str, vmid: int) -> dict:
        return {"user": "test@pve", "ticket": "PVE:fake", "port": "5900"}

    def delete_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_delete is not None:
            raise self.fallar_delete
        self.eliminados.append((node, int(vmid)))
        self.estados.pop(int(vmid), None)
        self.configuraciones.pop((node, int(vmid)), None)
        self.recursos = [r for r in self.recursos if int(r.get("vmid", -1)) != int(vmid)]
        for key, entries in self.contenidos_storage.items():
            if key[0] == node:
                self.contenidos_storage[key] = [entry for entry in entries if f'vm-{vmid}-disk-' not in entry['volid']]
        return self._task(node, vmid, 'delete')

    # --- Recursos del clúster ---

    def get_cluster_resources(self, resource_type: str | None = None) -> list[dict]:
        if self.fallar_recursos is not None:
            raise self.fallar_recursos
        if resource_type is None:
            return list(self.recursos)

        # Misma enumeración que la API real: pedir "lxc" devuelve 400. Que el
        # doble lo aceptara fue lo que dejó pasar un filtro imposible hasta
        # producción (los contenedores llegan dentro de "vm").
        if resource_type not in TIPOS_RECURSO_VALIDOS:
            raise ProxmoxFalla(
                f"400 Bad Request: Parameter verification failed. - value "
                f"'{resource_type}' does not have a value in the enumeration "
                f"'{', '.join(sorted(TIPOS_RECURSO_VALIDOS))}'"
            )

        if resource_type == "vm":
            return [r for r in self.recursos if r.get("type") in ("lxc", "qemu")]
        return [r for r in self.recursos if r.get("type") == resource_type]

    def listar_lxc_del_cluster(self) -> list[dict]:
        return [r for r in self.get_cluster_resources("vm") if r.get("type") == "lxc"]

    # --- Next VMID ---

    def get_next_vmid(self) -> int:
        self.llamadas_next_vmid += 1
        vmid = self.next_vmid
        self.next_vmid += 1
        return vmid

    def check_vmid_available(self, vmid):
        if any(int(row['vmid']) == int(vmid) for row in self.recursos):
            raise ProxmoxFalla('VMID ocupado')
        if any(key[1] == int(vmid) for key in self.configuraciones):
            raise ProxmoxFalla('Configuración existente')
        return int(vmid)


def ocupar(
    vmid: int, hostname: str, node: str = "pve1", status: str = "running"
) -> dict:
    """Construye una entrada de ``get_cluster_resources`` para un VMID ya tomado."""
    return {
        "type": "lxc",
        "vmid": vmid,
        "name": hostname,
        "node": node,
        "status": status,
    }


class FakeConsoleDirectory:
    """Representa el trabajo manual externo; no es una API PVE implementada."""
    def __init__(self):
        self.permissions = {}
        self.sessions = {}

    def open(self, identity, scope):
        if scope not in self.permissions.get(identity, set()):
            raise PermissionError('Sin permiso nativo')
        ticket = f'test-session-{len(self.sessions)}'
        self.sessions[ticket] = (identity, scope)
        return ticket

    def allows(self, ticket):
        entry = self.sessions.get(ticket)
        return bool(entry and entry[1] in self.permissions.get(entry[0], set()))

    def revoke(self, identity, remaining=()):
        self.permissions[identity] = set(remaining)
        self.sessions = {key: value for key, value in self.sessions.items() if value[0] != identity}
