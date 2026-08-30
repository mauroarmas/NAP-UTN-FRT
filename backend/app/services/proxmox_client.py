import time

from proxmoxer import ProxmoxAPI
from app.config import get_settings

# Cuánto esperar a que una tarea de Proxmox termine antes de darla por colgada.
# Crear un contenedor sobre una plantilla ya descargada tarda segundos; el margen
# cubre un clúster cargado sin dejar la petición esperando para siempre.
TASK_TIMEOUT_SEGUNDOS = 180
TASK_POLL_SEGUNDOS = 1.0


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

    def esperar_task(self, node: str, task_id: str) -> None:
        """Espera a que una tarea de Proxmox termine y falla si terminó mal.

        Las operaciones de Proxmox son **asíncronas**: la llamada devuelve un
        identificador de tarea y vuelve enseguida, mucho antes de que el trabajo
        real haya ocurrido. Sin esta espera, un fallo dentro de la tarea —una
        plantilla que no existe, un almacenamiento lleno, un VMID en conflicto—
        es completamente invisible para el portal, que registra el servicio como
        desplegado y en marcha mientras el clúster no creó nada.

        Ese desajuste rompe dos principios a la vez: el registro de un recurso
        que no existe (III) y un estado que no se corresponde con la realidad
        (II). Además consume capacidad reservada que ningún contenedor usa.
        """
        limite = time.monotonic() + TASK_TIMEOUT_SEGUNDOS
        while True:
            estado = self.api.nodes(node).tasks(task_id).status.get()
            if estado.get("status") == "stopped":
                salida = estado.get("exitstatus", "")
                # Proxmox usa "OK" para el éxito limpio y "WARNINGS: n" para el
                # éxito con advertencias (típico al arrancar un contenedor sin
                # algunas features del host). Ninguna de las dos es un fallo.
                if salida == "OK" or salida.startswith("WARNINGS"):
                    return
                raise RuntimeError(f"La tarea de Proxmox falló: {salida}")

            if time.monotonic() > limite:
                raise RuntimeError(
                    f"La tarea de Proxmox no terminó en {TASK_TIMEOUT_SEGUNDOS} s"
                )
            time.sleep(TASK_POLL_SEGUNDOS)

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        """Obtiene el estado actual de un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.current.get()

    def start_lxc(self, node: str, vmid: int) -> str:
        """Inicia un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.start.post()

    def stop_lxc(self, node: str, vmid: int) -> str:
        """Detiene un contenedor LXC."""
        return self.api.nodes(node).lxc(vmid).status.stop.post()

    def reboot_lxc(self, node: str, vmid: int) -> str:
        """Reinicia un contenedor LXC (apagado + encendido gestionado por Proxmox)."""
        return self.api.nodes(node).lxc(vmid).status.reboot.post()

    def abrir_termproxy(self, node: str, vmid: int) -> dict:
        """
        Pide a Proxmox un ticket de consola para un LXC.

        Devuelve ``{"user": ..., "ticket": ..., "port": ...}``, usado para abrir la
        conexión WebSocket saliente hacia el ``vncwebsocket`` de Proxmox (ver
        research.md R2/R3 de la spec 003). El navegador nunca ve esta respuesta.
        """
        return self.api.nodes(node).lxc(vmid).termproxy.post()

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

    def listar_lxc_del_cluster(self) -> list[dict]:
        """
        Todos los contenedores LXC del clúster, de todos los nodos, en una llamada.

        `cluster/resources` NO acepta `type=lxc`: su enumeración es
        `vm, storage, node, sdn` y responde 400 con cualquier otra cosa. Los
        contenedores llegan dentro de `vm`, cada fila con su propio campo
        `type` ("lxc" o "qemu"), así que el filtro va acá y no en el parámetro.
        """
        return [
            r for r in self.get_cluster_resources("vm") if r.get("type") == "lxc"
        ]

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
