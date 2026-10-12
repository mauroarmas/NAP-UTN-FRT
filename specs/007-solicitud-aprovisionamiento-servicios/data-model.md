# Data Model Specification

**Feature**: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS (`007-solicitud-aprovisionamiento-servicios`)  
**Status**: Completed  
**Date**: 2026-10-08  

---

## 1. Entidades y Esquema de Datos

### 1.1 `Pedido` (Extensión del Modelo Existente)

Representa la solicitud formal de recursos por parte de una cátedra.

| Campo | Tipo | Nulo | Descripción / Regla de Validación |
| :--- | :--- | :---: | :--- |
| `id` | Integer | No | Identificador único primario (autoincremental). |
| `catedra_id` | Integer (FK `catedras.id`) | No | Cátedra titular de la solicitud. Aislamiento por tenant (Principio IV). |
| `solicitante_id` | Integer (FK `usuarios.id`) | No | Docente que confeccionó la solicitud. |
| `modelo_servicio` | Enum (`iaas`, `paas`, `saas`) | No | Modelo de servicio del NIST solicitado. |
| `template_id` | Integer (FK `recurso_templates.id`) | Sí | Obligatorio para IaaS; opcional/sugerido para SaaS y PaaS (asignable por el Admin). |
| `descripcion_requerimientos` | Text | Sí | Obligatorio para SaaS/PaaS; descripción detallada del software, API o necesidades. |
| `vigencia_tipo` | Enum (`primer_cuatrimestre`, `segundo_cuatrimestre`, `anual`, `personalizado`) | No | Modalidad académica de duración solicitada. |
| `vigencia_desde` | DateTime | Sí | Fecha de inicio solicitada o estimada. |
| `vigencia_hasta` | DateTime | Sí | Fecha límite calculada o especificada. |
| `estado` | Enum (`EstadoPedido`) | No | Estado actual del ciclo de vida (default: `SOLICITADO`). |
| `tipo` | Enum (`alta`, `renovacion`) | No | Modalidad de pedido (default: `alta`). |
| `motivo_rechazo` | Text | Sí | Obligatorio para transición a `RECHAZADO`. |
| `observaciones_ajuste` | Text | Sí | Comentarios y contrapropuesta del Admin para estado `REQUIERE_AJUSTE`. |
| `opciones_avanzadas` | JSON | Sí | Parámetros técnicos avanzados asignados por el Admin en la aprobación. |
| `vmid_reservado` | String(10) | Sí | Identificador asignado en Proxmox antes de instanciar (recuperabilidad). |
| `reserva_vcpus` | Integer | No | vCPUs comprometidas atómicamente en la aprobación (Principio IV). |
| `reserva_ram_mb` | Integer | No | Memoria RAM comprometida atómicamente. |
| `reserva_disk_gb` | Integer | No | Almacenamiento comprometido atómicamente. |
| `reserva_expira_at` | DateTime | Sí | Plazo máximo de materialización de la reserva. |
| `justificacion_capacidad` | Text | Sí | Requerida si se aprueba por encima del límite libre del clúster. |
| `created_at` | DateTime | No | Marca temporal de creación (UTC). |
| `updated_at` | DateTime | No | Marca temporal de última modificación (UTC). |
| `resolved_at` | DateTime | Sí | Marca temporal de aprobación o rechazo final. |
| `deleted_at` | DateTime | Sí | Baja lógica (Principio V). |

---

### 1.2 `RecursoTemplate` (Extensión del Modelo Existente)

Catálogo de plantillas homologadas gestionadas mediante ABM por el Administrador.

| Campo | Tipo | Nulo | Descripción / Regla de Validación |
| :--- | :--- | :---: | :--- |
| `id` | Integer | No | Identificador único primario. |
| `nombre` | String(100) | No | Nombre identificador único (ej: *IaaS Small*, *IaaS Large*, *JupyterHub Base*). |
| `descripcion` | Text | Sí | Descripción de propósitos pedagógicos del template. |
| `modelo_servicio` | Enum (`iaas`, `paas`, `saas`) | No | Clasificación del modelo de servicio al que aplica la plantilla. |
| `tipo_virtualizacion` | Enum (`lxc`, `qemu`) | No | Tecnología subyacente en Proxmox VE (default: `lxc`). |
| `default_vcpus` | Integer | No | Cantidad de núcleos asignados por defecto ($\ge 1$). |
| `default_ram_mb` | Integer | No | Memoria asignada por defecto ($\ge 256$ MB). |
| `default_disk_gb` | Integer | No | Disco asignado por defecto ($\ge 1$ GB). |
| `justificacion_disco` | Text | Sí | **Obligatorio** si `default_disk_gb > 8` (Principio IV de la Constitución). |
| `os_template` | String(200) | Sí | Nombre de la imagen base/template en el storage de Proxmox. |
| `config_extra` | JSON | Sí | Variables de entorno predeterminadas, puertos expuestos o tags. |
| `activo` | Boolean | No | Control de visibilidad en el catálogo para nuevas solicitudes (default: `True`). |

---

### 1.3 `Servicio` (Extensión de Entidad Activa)

Representa el recurso instanciado y operativo en Proxmox VE.

| Campo | Tipo | Nulo | Descripción |
| :--- | :--- | :---: | :--- |
| `id` | Integer | No | Identificador único primario. |
| `catedra_id` | Integer (FK `catedras.id`) | No | Cátedra propietaria del servicio. |
| `pedido_id` | Integer (FK `pedidos.id`) | Sí | Pedido originario que generó el servicio (único). |
| `template_id` | Integer (FK `recurso_templates.id`) | No | Plantilla utilizada. |
| `proxmox_vmid` | String(10) | Sí | Identificador interno de Proxmox VE. |
| `proxmox_node` | String(50) | Sí | Nodo físico del clúster donde se ejecuta. |
| `estado` | Enum (`running`, `stopped`, `paused`, `error`) | No | Estado de ejecución en la infraestructura. |
| `ip_address` | String(45) | Sí | Dirección IP asignada en la red institucional. |
| `url_acceso` | String(255) | Sí | Enlace directo para consumo docente/estudiantil (SaaS/PaaS/Web). |
| `credenciales_acceso` | JSON | Sí | Tokens de API, usuario y contraseña inicial generada de forma segura. |
| `vence_at` | DateTime | Sí | Fecha de expiración pactada a partir de la vigencia del pedido. |
| `aviso_vencimiento_at` | DateTime | Sí | Notificación de proximidad de fin de ciclo. |
| `deployed_at` | DateTime | Sí | Momento de puesta en marcha operativa. |
| `deleted_at` | DateTime | Sí | Baja lógica (Principio V). |

---

### 1.4 `PedidoHistorial` (Inmutable / Append-Only)

Bitácora histórica exigida por el Principio II y V de la Constitución.

| Campo | Tipo | Nulo | Descripción |
| :--- | :--- | :---: | :--- |
| `id` | Integer | No | Identificador único de auditoría. |
| `pedido_id` | Integer (FK `pedidos.id`) | No | Pedido afectado. |
| `estado_anterior` | String(20) | No | Estado previo al evento. |
| `estado_nuevo` | String(20) | No | Estado resultante. |
| `comentario` | Text | Sí | Motivo de rechazo, notas de ajuste u observaciones del sistema. |
| `usuario_id` | Integer (FK `usuarios.id`) | Sí | Usuario autor de la transición (NULL si fue el sistema o scheduler). |
| `created_at` | DateTime | No | Marca temporal inmutable del suceso. |

---

## 2. Máquina de Estados Ampliada (`EstadoPedido`)

### 2.1 Tabla de Transiciones Válidas

```text
SOLICITADO
  ├──> APROBADO           [Admin: aprueba y reserva capacidad]
  ├──> REQUIERE_AJUSTE    [Admin: devuelve con observaciones]
  └──> RECHAZADO          [Admin: rechaza con motivo escrito]

REQUIERE_AJUSTE
  ├──> SOLICITADO         [Cátedra: ajusta y reenvía a evaluación]
  ├──> CANCELADO          [Cátedra: desiste de la solicitud]
  └──> RECHAZADO          [Admin: rechazo administrativo definitivo]

APROBADO
  ├──> EN_DESPLIEGUE      [Sistema/Orquestador: inicia clonación y arranque]
  └──> RECHAZADO          [Sistema: expira la reserva o reversión de aprobación]

EN_DESPLIEGUE
  ├──> ACTIVO             [Sistema/Orquestador: despliegue Proxmox exitoso]
  └──> ERROR              [Sistema/Orquestador: falla técnica en clúster]

ERROR
  ├──> EN_DESPLIEGUE      [Admin: reintento de aprovisionamiento]
  └──> RECHAZADO          [Admin: descarte definitivo con liberación de reserva]

ACTIVO
  └──> SUSPENDIDO         [Admin o Sistema: fin de ciclo o detención administrativa]

SUSPENDIDO
  └──> ACTIVO             [Admin o Sistema: reactivación]

RECHAZADO / CANCELADO
  └──> (Estados finales - inmutables)
```

---

## 3. Reglas de Validación Constitucional

1. **Garantía de Autoría y Trazabilidad (Principio II):**
   - Toda llamada a `cambiar_estado(...)` DEBE insertar una fila en `PedidoHistorial`.
   - Si la acción la ejecuta un proceso de fondo o el orquestador, `usuario_id` es `NULL` y el comentario documenta la causa del sistema.
2. **Control Atómico de Capacidad (Principio IV):**
   - La transición `SOLICITADO` $\rightarrow$ `APROBADO` debe verificar capacidad libre y crear la reserva en la misma transacción de base de datos.
3. **Tope de Almacenamiento (Principio IV):**
   - Ningún template o aprobación puede comprometer más de 8 GB de disco sin que exista texto registrado en `justificacion_disco`.
4. **Preservación Histórica (Principio V):**
   - Ninguna fila de `Pedido`, `Servicio` o `RecursoTemplate` se elimina mediante `DELETE` físico; se utiliza `deleted_at IS NOT NULL`.

