"""Doble de prueba del cliente Proxmox.

Permite ejercitar los caminos de fallo de infraestructura sin un clúster real,
como exige la compuerta de calidad de la constitución del proyecto.
"""


class ProxmoxFalla(Exception):
    """Error genérico de infraestructura, equivalente a lo que levanta proxmoxer."""


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
        fallar_delete: Exception | None = None,
        recursos: list[dict] | None = None,
        nodos: list[dict] | None = None,
    ):
        self.next_vmid = next_vmid
        self.fallar_create = fallar_create
        self.fallar_delete = fallar_delete
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
        self.llamadas_next_vmid = 0

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

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        return {"status": self.estados.get(int(vmid), "stopped")}

    def start_lxc(self, node: str, vmid: int) -> str:
        self.iniciados.append((node, int(vmid)))
        self.estados[int(vmid)] = "running"
        return f"UPID:{node}:task:start"

    def stop_lxc(self, node: str, vmid: int) -> str:
        self.detenidos.append((node, int(vmid)))
        self.estados[int(vmid)] = "stopped"
        return f"UPID:{node}:task:stop"

    def delete_lxc(self, node: str, vmid: int) -> str:
        if self.fallar_delete is not None:
            raise self.fallar_delete
        self.eliminados.append((node, int(vmid)))
        self.estados.pop(int(vmid), None)
        self.recursos = [r for r in self.recursos if int(r.get("vmid", -1)) != int(vmid)]
        return f"UPID:{node}:task:delete"

    # --- Recursos del clúster ---

    def get_cluster_resources(self, resource_type: str | None = None) -> list[dict]:
        if resource_type:
            return [r for r in self.recursos if r.get("type") == resource_type]
        return list(self.recursos)

    # --- Next VMID ---

    def get_next_vmid(self) -> int:
        self.llamadas_next_vmid += 1
        vmid = self.next_vmid
        self.next_vmid += 1
        return vmid


def ocupar(vmid: int, hostname: str, node: str = "pve1") -> dict:
    """Construye una entrada de ``get_cluster_resources`` para un VMID ya tomado."""
    return {
        "type": "lxc",
        "vmid": vmid,
        "name": hostname,
        "node": node,
        "status": "running",
    }
