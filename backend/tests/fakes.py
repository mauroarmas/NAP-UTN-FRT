"""Doble de prueba del cliente Proxmox.

Permite ejercitar los caminos de fallo de infraestructura sin un clúster real,
como exige la compuerta de calidad de la constitución del proyecto.
"""


class ProxmoxFalla(Exception):
    """Error genérico de infraestructura, equivalente a lo que levanta proxmoxer."""


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

    # --- Nodos ---

    def get_nodes(self) -> list[dict]:
        return self.nodos

    # --- Contenedores LXC ---

    def create_lxc(self, node: str, **kwargs) -> str:
        if self.fallar_create is not None:
            raise self.fallar_create
        self.creados.append({"node": node, **kwargs})
        vmid = int(kwargs.get("vmid", self.next_vmid))
        self.estados[vmid] = "running"
        # Reflejar el contenedor recién creado en los recursos del clúster
        self.recursos.append(
            {
                "type": "lxc",
                "vmid": vmid,
                "name": kwargs.get("hostname"),
                "node": node,
                "status": "running",
            }
        )
        return f"UPID:{node}:task:create"

    def esperar_task(self, node, task_id):
        if self.fallar_task is not None:
            raise self.fallar_task
        self.tasks_esperadas.append((node, task_id))

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        return {"status": self.estados.get(int(vmid), "stopped")}

    def start_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_start is not None:
            raise self.fallar_start
        self.iniciados.append((node, int(vmid)))
        self.estados[int(vmid)] = "running"
        return f"UPID:{node}:task:start"

    def stop_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_stop is not None:
            raise self.fallar_stop
        self.detenidos.append((node, int(vmid)))
        self.estados[int(vmid)] = "stopped"
        return f"UPID:{node}:task:stop"

    def reboot_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_reboot is not None:
            raise self.fallar_reboot
        self.reiniciados.append((node, int(vmid)))
        return f"UPID:{node}:task:reboot"

    def abrir_termproxy(self, node: str, vmid: int) -> dict:
        return {"user": "test@pve", "ticket": "PVE:fake", "port": "5900"}

    def delete_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_delete is not None:
            raise self.fallar_delete
        self.eliminados.append((node, int(vmid)))
        self.estados.pop(int(vmid), None)
        self.recursos = [r for r in self.recursos if int(r.get("vmid", -1)) != int(vmid)]
        return f"UPID:{node}:task:delete"

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
