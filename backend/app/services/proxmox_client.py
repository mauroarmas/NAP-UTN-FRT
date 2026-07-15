from proxmoxer import ProxmoxAPI
from app.config import get_settings


class ProxmoxClient:
    """Wrapper sobre proxmoxer para interactuar con la API de Proxmox VE."""

    def __init__(self):
        settings = get_settings()
        self.api = ProxmoxAPI(
            settings.proxmox_host,
            port=settings.proxmox_port,
            user=settings.proxmox_user,
            token_name=settings.proxmox_token_name,
            token_value=settings.proxmox_token_value,
            verify_ssl=settings.proxmox_verify_ssl,
            service="PVE",
        )

    # --- Nodos ---

    def get_nodes(self) -> list[dict]:
        """Obtiene la lista de nodos del clúster."""
        return self.api.nodes.get()

    def get_node_status(self, node: str) -> dict:
        """Obtiene el estado de un nodo específico."""
        return self.api.nodes(node).status.get()

    # --- Contenedores LXC ---

    def list_lxc(self, node: str) -> list[dict]:
        """Lista todos los contenedores LXC de un nodo."""
        return self.api.nodes(node).lxc.get()

    def create_lxc(self, node: str, **kwargs) -> str:
        """Crea un contenedor LXC. Proxmox asigna el VMID automáticamente."""
        return self.api.nodes(node).lxc.create(**kwargs)

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        """Obtiene el estado actual de un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.current.get()

    def start_lxc(self, node: str, vmid: int) -> str:
        """Inicia un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.start.post()

    def stop_lxc(self, node: str, vmid: int) -> str:
        """Detiene un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.stop.post()

    def delete_lxc(self, node: str, vmid: int) -> str:
        """Elimina un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).delete()

    # --- VMs QEMU ---

    def list_qemu(self, node: str) -> list[dict]:
        """Lista todas las VMs QEMU de un nodo."""
        return self.api.nodes(node).qemu.get()

    def get_qemu_status(self, node: str, vmid: int) -> dict:
        """Obtiene el estado actual de una VM QEMU."""
        return self.api.nodes(node).qemu(vmid).status.current.get()

    def start_qemu(self, node: str, vmid: int) -> str:
        """Inicia una VM QEMU."""
        return self.api.nodes(node).qemu(vmid).status.start.post()

    def stop_qemu(self, node: str, vmid: int) -> str:
        """Detiene una VM QEMU."""
        return self.api.nodes(node).qemu(vmid).status.stop.post()

    # --- Recursos del clúster ---

    def get_cluster_resources(self, resource_type: str | None = None) -> list[dict]:
        """Obtiene todos los recursos del clúster (VMs, CTs, nodos, storage)."""
        if resource_type:
            return self.api.cluster.resources.get(type=resource_type)
        return self.api.cluster.resources.get()

    def get_cluster_status(self) -> list[dict]:
        """Obtiene el estado general del clúster."""
        return self.api.cluster.status.get()

    # --- Storage ---

    def get_storage(self, node: str) -> list[dict]:
        """Obtiene información de almacenamiento de un nodo."""
        return self.api.nodes(node).storage.get()

    # --- Templates disponibles ---

    def get_available_templates(self, node: str, storage: str = "local") -> list[dict]:
        """Lista los templates de contenedores disponibles en un storage."""
        return self.api.nodes(node).storage(storage).content.get()

    # --- Next VMID ---

    def get_next_vmid(self) -> int:
        """Obtiene el próximo VMID disponible en el clúster."""
        return self.api.cluster.nextid.get()


# Singleton
_proxmox_client: ProxmoxClient | None = None


def get_proxmox_client() -> ProxmoxClient:
    """Obtiene o crea la instancia del cliente Proxmox."""
    global _proxmox_client
    if _proxmox_client is None:
        _proxmox_client = ProxmoxClient()
    return _proxmox_client
