# Implementation Plan: Usuario no root en la consola de Linux IaaS

**Branch**: `021-consola-usuario-no-root` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-consola-usuario-no-root/spec.md`

## Summary

Hoy el portal genera una contraseña (`guest_password`) al desplegar un Linux IaaS, se la pasa a Proxmox como contraseña de `root` al crear el contenedor y la entrega en «Revelar acceso inicial» con el usuario `root`. La feature 017 ya deja un usuario `nap` con `sudo` y clave SSH, pero con la contraseña bloqueada. El plan **reutiliza el mismo secreto y el mismo canal**: deja de pasarle contraseña a Proxmox al crear (así `root` no tiene contraseña), y la acción `configure` del runner de la 017 (`nap-iaas-access/1`) recibe un campo opcional `password_consola` con el que fija la contraseña de `nap` por entrada estándar y deja `root` bloqueado. El portal pasa a mostrar `nap` en el acceso inicial.

Para servicios ya entregados se agrega una acción de administración que encola una operación `reparar` con una contraseña **nueva** guardada cifrada **antes** de enviarla; sólo tras la confirmación del nodo se promueve a credencial del servicio y se cambia el usuario mostrado. Un resultado incierto se reintenta con la misma contraseña, así que es idempotente. No se toca ningún archivo que entre en el `policy_digest` del motor Docker. Detalle y fuentes en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (backend FastAPI + SQLAlchemy async; runner de nodo sólo biblioteca estándar), JavaScript/React (frontend Vite)

**Primary Dependencies**: las existentes. Sin dependencias nuevas.

**Storage**: PostgreSQL del portal **sin migración**: la credencial sigue en `servicios.credenciales_encrypted`; el usuario mostrado y el marcador de consola van en `servicios.acceso_metadata`; la contraseña pendiente de una reparación va cifrada en `operaciones_infraestructura.contexto_seguro`.

**Testing**: pytest (backend y `infra/runner/tests`, PostgreSQL de pruebas), vitest, y ensayo real en frt y pve91 (servicio nuevo y servicio entregado por actualización).

**Target Platform**: portal en contenedores del equipo; nodos Proxmox VE 9.x con LXC `unprivileged` Ubuntu 24.04 y Debian 13.

**Project Type**: aplicación web (backend + frontend) con paquete de infraestructura de nodo.

**Performance Goals**: sin sobrecosto perceptible: el paso extra de contraseña forma parte de la misma ejecución de `configure` (< 60 s en el laboratorio, como la 017).

**Constraints**: no modificar archivos que entran en el `policy_digest` del motor Docker (guarda `test_policy_digest_estable`); contraseña sólo por stdin/cifrada y nunca en `argv`, registros, errores ni auditoría (SC-005); `sshd` sin contraseñas ni `root`; compuerta y consola de la 020 y acceso SSH por clave de la 017 sin cambios de comportamiento; orden de instalación: nodos antes que portal.

**Scale/Scope**: decenas de servicios por cátedra; una credencial por servicio. Fuera de alcance: terminal web, más usuarios, rotación periódica, Docker/OCI, quitar el `sudo` sin contraseña.

## Constitution Check

*GATE: pasa antes de la investigación y se re-evalúa después del diseño.*

| Principio | Evaluación |
|---|---|
| I. Proxmox es el back-end | **Cumple.** No agrega derivaciones a Proxmox ni usa sus permisos; la excepción de consola no se toca. Toda operación pasa por `app/services/`; los routers no invocan `proxmoxer`. Sólo deja de enviarse una contraseña en la creación. |
| II. Máquina de estados única | **Cumple.** Sin estados nuevos de pedido; la actualización es una operación `reparar` con las transiciones e historial existentes y motivo/autor registrados. |
| III. Recuperable | **Cumple con atención (riesgo principal R5).** La contraseña nueva se persiste cifrada antes del envío; el runner es idempotente (fija si está bloqueada, no cambia si coincide); un resultado incierto se reintenta con el mismo secreto sin duplicar efectos ni dejar el acceso a medias. |
| IV. Aislamiento por cátedra | **Cumple.** El runner verifica `vmid`, nodo, pool, `resource_uuid` y nonce antes de tocar el contenedor (igual que la 017); la entrega sigue limitada a quien tiene acceso al servicio. |
| V–VI | No aplican (sin cambios de vigencia ni catálogo). Se revisarán en `/speckit-analyze`. |
| VII. Simplicidad | **Cumple.** La persona no aporta datos nuevos: el mismo «Revelar acceso inicial» muestra el usuario correcto. Una acción de administración para los servicios existentes; una sola cuenta (`nap`), sin opciones. |
| Seguridad | Contraseña aleatoria de 43 caracteres; viaja por stdin hasta `chpasswd`; `root` con `*`; `sshd` sigue sin contraseña (`PasswordAuthentication no`); revelación auditada sin valor. |

**Re-evaluación posterior al diseño**: sin violaciones. No se añade complejidad que requiera justificación.

## Project Structure

### Documentation (this feature)

```text
specs/021-consola-usuario-no-root/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── runner-iaas-access.md
    └── api-acceso-consola.md
```

### Source Code (repository root)

```text
backend/app/
├── schemas/iaas_access.py              # campo opcional `password_consola` en `configure` (copiado al nodo)
├── services/
│   ├── orquestacion_service.py         # no enviar `password` a Proxmox al crear; usuario `nap` en acceso_metadata; promover credencial
│   ├── iaas_acceso_service.py          # `aplicar` envía la contraseña; `actualizar_acceso_consola` (nueva acción de administración)
│   └── service_access_service.py       # sin cambios de lógica: el usuario sale de acceso_metadata
├── routers/servicios.py                # POST /servicios/{id}/acceso-consola (administración)
infra/runner/iaas_access.py             # fijar contraseña de `nap` por stdin, bloquear `root`, verificar, resultado sin secretos
frontend/src/components/AccesoServicio.jsx   # indicación según el usuario real; acción de administración
backend/tests/ + infra/runner/tests/    # pruebas nuevas
docs/infraestructura-laboratorio/scripts/portal/portal_ops.py   # comando de actualización para el laboratorio
docs/runbook-consola-nativa.md          # actualizar el paso de credenciales dentro de la consola
```

**Structure Decision**: se mantiene la estructura de la 017. No hay tablas ni migraciones; el cambio vive en el protocolo del runner, en dos servicios del backend y en un endpoint de administración.

## Complexity Tracking

Sin violaciones que justificar.
