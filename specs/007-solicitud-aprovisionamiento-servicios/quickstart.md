# Quickstart & End-to-End Validation Guide

**Feature**: Solicitud y Aprovisionamiento de Servicios IaaS, PaaS y SaaS (`007-solicitud-aprovisionamiento-servicios`)  
**Status**: Completed  
**Date**: 2026-10-08  

Este documento describe los escenarios de validación ejecutables para verificar de punta a punta la implementación de la feature, abarcando desde la solicitud hasta la autogestión y el ABM de templates.

---

## 1. Prerrequisitos y Entorno

1. Servidor de backend en ejecución (FastAPI) y base de datos PostgreSQL migrada con Alembic.
2. Clúster Proxmox VE accesible (o entorno de pruebas con mock Proxmoxer).
3. Usuarios de prueba creados:
   - `admin@utn.edu.ar` (Rol: Administrador).
   - `docente@utn.edu.ar` (Rol: Cátedra, asignado a una cátedra activa).

---

## 2. Escenarios de Validación

### Escenario 1: Flujo Principal IaaS (Creación, Aprobación y Aprovisionamiento)

- **Objetivo**: Validar el Happy Path completo para una solicitud de cómputo base.
- **Pasos**:
  1. Iniciar sesión como docente y enviar `POST /api/v1/pedidos`:
     - `modelo_servicio`: `"iaas"`, `template_id`: ID del template *Small*, `vigencia_tipo`: `"primer_cuatrimestre"`.
  2. Verificar respuesta `201 Created` con `estado: "solicitado"` y código de seguimiento.
  3. Iniciar sesión como administrador y consultar `GET /api/v1/pedidos?estado=solicitado`.
  4. Ejecutar `POST /api/v1/pedidos/{id}/aprobar` con `{ "template_id": ... }`.
  5. Verificar que el pedido transiciona a `en_despliegue` y luego a `activo`.
  6. Consultar `GET /api/v1/servicios` con el usuario docente y validar presencia del nuevo servicio con IP asignada.

---

### Escenario 2: Solicitud SaaS / PaaS con Opciones Avanzadas

- **Objetivo**: Validar el aprovisionamiento de un servicio especializado con personalización técnica administrativa.
- **Pasos**:
  1. El docente envía `POST /api/v1/pedidos`:
     - `modelo_servicio`: `"saas"`, `descripcion_requerimientos`: `"Libro virtual interactivo para cátedra de Sistemas Operativos"`, `vigencia_tipo`: `"anual"`.
  2. El administrador revisa la solicitud y aprueba con opciones avanzadas en `POST /api/v1/pedidos/{id}/aprobar`:
     - `opciones_avanzadas`: `{ "nodo_destino": "pve-node-01", "vlan_tag": 100 }`.
  3. Comprobar que el servicio queda operativo con URL de acceso directo y credenciales emitidas.

---

### Escenario 3: Flujo de Negociación y Ajuste (`REQUIERE_AJUSTE`)

- **Objetivo**: Validar la devolución colaborativa de pedidos entre Administrador y Cátedra.
- **Pasos**:
  1. Docente envía solicitud con recursos elevados.
  2. Administrador ejecuta `POST /api/v1/pedidos/{id}/solicitar-ajuste` con:
     - `observaciones`: `"Capacidad reducida en memoria RAM; se sugiere ajustar a 4GB."`.
  3. Verificar que el estado del pedido cambia a `requiere_ajuste` y queda registrado en `pedidos_historial`.
  4. Docente consulta el pedido, modifica la solicitud y ejecuta `POST /api/v1/pedidos/{id}/reenviar`.
  5. Verificar que el estado retorna a `solicitado` listo para nueva evaluación.

---

### Escenario 4: Rechazo Fundado con Motivo Obligatorio

- **Objetivo**: Asegurar que ningún pedido sea rechazado sin justificación escrita.
- **Pasos**:
  1. Administrador intenta `POST /api/v1/pedidos/{id}/rechazar` con cuerpo vacío o motivo menor a 5 caracteres.
  2. Verificar error de validación `422 Unprocessable Entity`.
  3. Administrador reintenta enviando motivo fundado: `"Solicitud no corresponde a actividades curriculares aprobadas."`.
  4. Verificar respuesta exitosa, estado `rechazado` y auditoría inmutable.

---

### Escenario 5: ABM de Templates y Validación de Capacidad

- **Objetivo**: Validar la gestión de plantillas y el cumplimiento del límite de almacenamiento constitucional (Principio IV).
- **Pasos**:
  1. Administrador envía `POST /api/v1/templates` con `default_disk_gb: 10` sin campo `justificacion_disco`.
  2. Verificar que el sistema rechaza la creación con error de validación.
  3. Administrador reintenta agregando `justificacion_disco: "Requerido para imágenes ISO de laboratorio"`.
  4. Verificar creación exitosa del template en catálogo.
  5. Administrador ejecuta `DELETE /api/v1/templates/{id}` y comprueba baja lógica (`activo: false`).

---

### Escenario 6: Autogestión de Servicios (Reinicio y Métricas)

- **Objetivo**: Comprobar las operaciones de ciclo de vida del servicio desplegado.
- **Pasos**:
  1. Docente ejecuta `POST /api/v1/servicios/{id}/reboot`.
  2. Verificar que la orden se envía a Proxmox VE y retorna confirmación.
  3. Docente consulta `GET /api/v1/servicios/{id}/metricas` y verifica carga de CPU y memoria.

