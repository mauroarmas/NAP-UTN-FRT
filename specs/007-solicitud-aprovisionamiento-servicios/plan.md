# Implementation Plan: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS

**Branch**: `007-solicitud-aprovisionamiento-servicios` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-solicitud-aprovisionamiento-servicios/spec.md`

---

## Summary

Implementar el ciclo integral de solicitud, evaluación, aprobación con despliegue automatizado y autogestión de servicios para cátedras bajo los modelos IaaS, PaaS y SaaS. Incorpora el soporte de vigencia temporal académica, opciones técnicas avanzadas para el Administrador, un flujo colaborativo de negociación y ajustes de solicitudes (`REQUIERE_AJUSTE`), el catálogo ABM de templates homologados y los controles de autogestión de servicios para los docentes.

---

## Technical Context

**Language/Version**: Python 3.12 (Backend) / JavaScript / React 18 (Frontend)  
**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic, Proxmoxer
- Frontend: React 18, Vite, React Router, TailwindCSS / Lucide Icons  
**Storage**: PostgreSQL 16 (on-premise)  
**Testing**: `pytest`, `pytest-asyncio`, `httpx` (contract & API tests)  
**Target Platform**: Servidores locales on-premise UTN-FRT sobre clúster Proxmox VE con almacenamiento NAS y redes VLAN/SDN  
**Project Type**: Aplicación Web Cliente-Servidor (Portal de Autoservicio y Orquestación Cloud)  
**Performance Goals**: Despliegue automatizado de plantillas estándar en menos de 5 minutos; respuesta de API en operaciones de consulta $< 200$ ms  
**Constraints**: Aislamiento estricto por cátedra; límite constitucional de 8 GB de disco por contenedor sin justificación explícita; preservación histórica append-only  
**Scale/Scope**: Más de 20 cátedras activas, cientos de contenedores concurrentes por nodo  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Estado | Justificación / Cumplimiento en el Diseño |
| :--- | :---: | :--- |
| **I. Proxmox es el back-end, nunca la interfaz** | **PASA** | La Cátedra y el Administrador operan 100% a través del portal de gestión. Los alumnos consumen los servicios directamente en la red institucional sin cuentas en el portal. No se expone Proxmox salvo la consola del contenedor propio ya contemplada. |
| **II. La máquina de estados es la única fuente de verdad** | **PASA** | Todas las transiciones (incluyendo los nuevos estados `REQUIERE_AJUSTE` y `CANCELADO`) se concentran en `pedido_service.cambiar_estado`. Toda transición genera registro en `PedidoHistorial` con autor y motivo. |
| **III. Toda operación contra la infraestructura debe ser recuperable** | **PASA** | Se preserva la reserva de capacidad atómica, la asignación de `vmid_reservado` previa al despliegue y la liberación automática de capacidad ante fallas o cancelaciones. |
| **IV. Aislamiento por cátedra; la capacidad se controla al aprobar** | **PASA** | La cátedra solo accede a sus propios pedidos y servicios. No hay cuotas fijas previas; la capacidad se valida y reserva atómicamente al confirmar la aprobación. Los templates con disco $> 8$ GB exigen justificación obligatoria. |
| **V. El historial académico no se destruye** | **PASA** | Bajas lógicas (`deleted_at`) en pedidos, servicios y templates. La bitácora de transiciones y observaciones es estrictamente inmutable y append-only. |

---

## Project Structure

### Documentation (this feature)

```text
specs/007-solicitud-aprovisionamiento-servicios/
├── spec.md              # Especificación de requerimientos y casos de usuario
├── plan.md              # Este plan de implementación arquitectónica
├── research.md          # Decisiones de arquitectura y alternativas evaluadas
├── data-model.md        # Esquema de datos, entidades y máquina de estados
├── quickstart.md        # Guía paso a paso de validación punta a punta
├── checklists/
│   └── requirements.md  # Checklist de calidad de la especificación
└── contracts/
    ├── pedidos.yaml     # Contrato OpenAPI para solicitudes, aprobación y ajustes
    ├── templates.yaml   # Contrato OpenAPI para ABM de plantillas de recursos
    └── servicios.yaml   # Contrato OpenAPI para autogestión y consumo de servicios
```

### Source Code Layout

```text
backend/
├── alembic/versions/              # Migración para modelo_servicio, vigencia y estados
├── app/
│   ├── models/
│   │   ├── pedido.py              # Extensión con modelo_servicio, vigencia y REQUIERE_AJUSTE
│   │   ├── recurso_template.py    # Extensión para catálogo y categorización
│   │   └── servicio.py            # Extensión para endpoints, credenciales y vigencia
│   ├── schemas/
│   │   ├── pedido.py              # Esquemas Pydantic v2 para solicitud y opciones avanzadas
│   │   ├── template.py            # Esquemas Pydantic v2 para ABM de plantillas
│   │   └── servicio.py            # Esquemas Pydantic v2 para autogestión y accesos
│   ├── services/
│   │   ├── pedido_service.py      # Transiciones centralizadas y validación de estados
│   │   ├── orquestacion_service.py # Aprovisionamiento automático y opciones avanzadas
│   │   └── capacidad_service.py   # Reserva atómica y verificación en clúster
│   └── routers/
│       ├── pedidos.py             # Endpoints /pedidos, /aprobar, /rechazar, /solicitar-ajuste
│       ├── templates.py           # Endpoints CRUD para gestión de templates
│       └── servicios.py           # Endpoints de autogestión (start/stop/reboot/métricas)

frontend/
├── src/
│   ├── components/
│   │   ├── NuevoPedidoModal.jsx   # Formulario con IaaS/PaaS/SaaS y vigencia
│   │   ├── AprobarPedidoModal.jsx # Selección de template y Opciones Avanzadas
│   │   ├── AjustePedidoModal.jsx  # Observaciones de contrapropuesta y reenvío
│   │   └── TemplatesAdmin.jsx     # Panel ABM de gestión de plantillas
│   └── pages/
│       ├── PedidosPage.jsx        # Bandeja de pedidos con filtrado por estado y modelo
│       └── ServiciosPage.jsx      # Panel de autogestión con métricas y controles
```

---

## Complexity Tracking

> **Sin violaciones a la constitución.** Todas las extensiones se apoyan en los modelos, servicios y convenciones consolidadas del proyecto.
