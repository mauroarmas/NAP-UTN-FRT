# Technical Research & Architectural Decisions

**Feature**: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS (`007-solicitud-aprovisionamiento-servicios`)  
**Status**: Completed  
**Date**: 2026-10-08  

---

## 1. Contexto de Investigación

Esta fase resuelve los aspectos técnicos requeridos para implementar el ciclo de vida ampliado de pedidos y servicios bajo los modelos IaaS, PaaS y SaaS sobre el clúster Proxmox VE de la UTN-FRT, garantizando el cumplimiento estricto de la Constitución del proyecto (Principios I a V) y las definiciones del relevamiento.

---

## 2. Decisiones Arquitectónicas

### Decisión 1: Estructuración de Modelos de Servicio (IaaS, PaaS, SaaS) y Vigencia Temporal

- **Decisión**: Extender la entidad `Pedido` con:
  - `modelo_servicio`: Enum (`iaas`, `paas`, `saas`).
  - `descripcion_requerimientos`: Texto libre obligatorio para SaaS/PaaS y complementario para IaaS.
  - `vigencia_tipo`: Enum (`primer_cuatrimestre`, `segundo_cuatrimestre`, `anual`, `personalizado`).
  - `vigencia_desde` y `vigencia_hasta`: Marcas de tiempo de vigencia efectiva.
  - Para IaaS: la selección de `template_id` es obligatoria desde el catálogo de tamaños (*Small*, *Medium*, *Large*). Para SaaS y PaaS: `template_id` puede seleccionarse a partir de templates específicos de software/API o ser asignado/definido por el Administrador al momento de la aprobación técnica.
- **Justificación**: Convierte los modelos del NIST (SP 800-145) y la temporalidad académica en atributos formales y tipados del modelo de datos, permitiendo consultas analíticas, reportes pedagógicos y cálculo automático de expiración de servicios.
- **Alternativas consideradas**:
  - *Almacenar todo dentro del JSON `parametros_extra`:* Rechazado porque degrada la integridad referencial, dificulta las consultas de auditoría y debilita las validaciones Pydantic en los contratos API.

---

### Decisión 2: Máquina de Estados para Ajustes y Negociación (`REQUIERE_AJUSTE`)

- **Decisión**: Incorporar los estados `REQUIERE_AJUSTE` y `CANCELADO` al enum `EstadoPedido`, respetando la función centralizada de transición `pedido_service.cambiar_estado`:
  - `SOLICITADO` $\rightarrow$ `REQUIERE_AJUSTE`: Disparado por el Administrador al devolver el pedido con observaciones obligatorias.
  - `REQUIERE_AJUSTE` $\rightarrow$ `SOLICITADO`: Disparado por la Cátedra al editar los requerimientos y reenviar a aprobación.
  - `REQUIERE_AJUSTE` $\rightarrow$ `CANCELADO`: Disparado por la Cátedra si decide desestimar la solicitud tras la contrapropuesta.
  - `REQUIERE_AJUSTE` $\rightarrow$ `RECHAZADO`: Disparado por el Administrador si se agota la negociación sin acuerdo.
- **Justificación**: Cumple con el Principio II de la Constitución (*"La máquina de estados es la única fuente de verdad"*). El estado refleja con exactitud en manos de quién está la acción, impidiendo que el pedido quede estancado en `SOLICITADO` mientras la cátedra evalúa los cambios.
- **Alternativas consideradas**:
  - *Manejar ajustes mediante comentarios sin cambiar el estado `SOLICITADO`:* Rechazado porque violaría el Principio II, ocultando a la administración qué pedidos están listos para evaluar y cuáles están siendo modificados por los docentes.

---

### Decisión 3: Despliegue Automatizado con Opciones Avanzadas

- **Decisión**: Enriquecer el endpoint `POST /pedidos/{id}/aprobar` permitiendo un payload estructurado opcional con `opciones_avanzadas`:
  - `nodo_destino`: Nodo físico de Proxmox VE seleccionado (opcional; si es null, el balanceador asigna por capacidad libre).
  - `storage_pool`: Almacenamiento NAS/local de Proxmox (opcional; default según template).
  - `vlan_id` / `sdn_zone`: Parámetros de aislamiento de red (opcional).
  - `override_vcpus`, `override_ram_mb`, `override_disk_gb`: Ajustes finos de capacidad aprobada.
- **Justificación**: Cumple el requerimiento de negocio: el sistema despliega 100% automático por defecto con el template homologado, pero el Administrador dispone de un panel plegable de "Opciones Avanzadas" para resolver casos particulares de infraestructura. La reserva de capacidad en DB se actualiza atómicamente con los valores definitivos aprobados (Principio IV).
- **Alternativas consideradas**:
  - *Obligar al admin a modificar la plantilla global cada vez que requiere un parámetro específico:* Rechazado porque afectaría a otros pedidos futuros y rompería la consistencia del catálogo de templates.

---

### Decisión 4: Módulo ABM de Plantillas (Templates de Recursos)

- **Decisión**: Implementar el ciclo completo de administración de plantillas (`RecursoTemplate`):
  - Endpoints administrativos: `GET /api/v1/templates` (filtrado por activos/inactivos), `POST /api/v1/templates` (alta), `PUT /api/v1/templates/{id}` (modificación de parámetros default), `DELETE /api/v1/templates/{id}` (baja lógica / desactivación).
  - Regla constitucional de disco: Validación estricta que exige `justificacion_disco` obligatoria si `default_disk_gb > 8` (Principio IV).
  - Interfaz: Módulo dedicado en el panel del Administrador con formulario de configuración de vCPU, RAM, disco, imagen OS/template de Proxmox y tipo de servicio (IaaS/PaaS/SaaS).
- **Justificación**: Permite al equipo de infraestructura ajustar los tamaños predefinidos (*Small*, *Medium*, *Large*, etc.) sin necesidad de desplegar nuevas versiones de código ni migraciones manuales de base de datos.
- **Alternativas consideradas**:
  - *Hardcodear los tamaños en el frontend:* Rechazado porque elimina la flexibilidad operativa del equipo de infraestructura de la UTN-FRT.

---

### Decisión 5: Entrega de Credenciales y Desacoplamiento de Alumnos

- **Decisión**:
  - El objeto `Servicio` expone de forma clara los campos de conexión: `ip_address`, `hostname`, `url_acceso` y `credenciales_acceso` (o token de API para PaaS).
  - El docente de cátedra visualiza estos datos en su panel `Mis Servicios` y es el encargado de proveer los accesos a sus alumnos (por ejemplo, compartiendo el enlace al libro virtual, la IP del laboratorio o el endpoint de la API).
  - Los alumnos consumen la infraestructura directamente por la red universitaria (Principio I), sin requerir cuentas de usuario en el portal de gestión de NAP.
- **Justificación**: Mantiene el portal enfocado en la gobernanza y asignación de recursos, evitando sobrecargar el sistema con la gestión de miles de cuentas de estudiantes que solo necesitan consumir los servicios ya instanciados.

