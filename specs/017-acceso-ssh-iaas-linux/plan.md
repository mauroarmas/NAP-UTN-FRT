# Implementation Plan: Acceso SSH a servicios IaaS Linux

**Branch**: `017-acceso-ssh-iaas-linux` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-acceso-ssh-iaas-linux/spec.md`

## Summary

Hoy un Ubuntu IaaS entregado solo ofrece la consola web, que está bloqueada por una compuerta institucional. La persona aporta su clave pública SSH
al pedir el servicio; el portal la valida y la guarda (solo material público); una acción nueva y cerrada del runner del nodo
(`nap-iaas-access/1`) crea dentro del contenedor el usuario `nap` con elevación, instala solo esa clave y endurece `sshd` (sin contraseña ni
root); el servicio no se declara utilizable hasta que el chequeo local lo confirma. La misma acción, ejecutada como operación durable idempotente
por revisión, cubre el reemplazo de clave y los servicios ya entregados. El detalle de acceso agrega un bloque `acceso_ssh` sin tocar `metodo`
ni la compuerta de consola. Se respeta una restricción dura: no modificar ningún archivo que entre en el `policy_digest` del motor Docker, de modo
que los perfiles validados siguen vigentes. Detalle y fuentes en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (backend FastAPI + SQLAlchemy async; runner de nodo solo biblioteca estándar), JavaScript/React (frontend Vite)

**Primary Dependencies**: las existentes (FastAPI, SQLAlchemy, Alembic, proxmoxer, `cryptography` solo si ya está; si no, `hashlib`/`base64`). Sin dependencias nuevas.

**Storage**: PostgreSQL del portal: tabla nueva `claves_acceso_servicio`; tipo nuevo `acceso_ssh` en `operaciones_infraestructura`; migración Alembic (cabeza actual `010_06_acceso_aplicacion` / cadena hasta `c7d8e9f0a1b2`: verificar la cabeza real con `alembic heads`).

**Testing**: pytest (backend y `infra/runner/tests`, PostgreSQL de pruebas con `docker-compose.test.yml`), vitest/testing-library (frontend `tests/`), ensayo real en frt y pve91.

**Target Platform**: portal en contenedores del equipo; nodos Proxmox VE 9.x con LXC `unprivileged` Ubuntu 24.04.

**Project Type**: aplicación web (backend + frontend) con paquete de infraestructura de nodo.

**Performance Goals**: pasar de «servicio disponible» a terminal abierta en < 2 min (SC-001); la acción `configure` + `probe` termina en < 60 s en el laboratorio.

**Constraints**: ninguna clave privada ni contraseña en pantalla, historial, errores ni registros (SC-006); no alterar `policy_digest` (R4); sin cambios de comportamiento en Docker/OCI, bases ni aplicaciones web (FR-014); la consola IaaS y su compuerta quedan como están (FR-015); la acción del runner es idempotente por revisión y falla cerrada ante cualquier duda de identidad.

**Scale/Scope**: decenas de servicios por cátedra; una clave por servicio. Fuera de alcance: terminal web, restricción de red por instancia, varias claves, Docker/OCI.

## Constitution Check

*GATE: pasa antes de la investigación y se re-evalúa después del diseño.*

| Principio | Evaluación |
|---|---|
| I. Proxmox es el back-end | **Cumple.** El acceso no deriva a ninguna pantalla de Proxmox ni usa sus permisos. Toda operación pasa por `app/services/`; los routers no invocan `proxmoxer`. La excepción única de la consola interactiva no se amplía ni se usa como precedente (FR-009, FR-015). |
| II. Máquina de estados única | **Cumple.** La clave no introduce estados de pedido; el estado `pendiente/aplicada` es derivado. La operación `acceso_ssh` usa las transiciones y el historial existentes; los fallos quedan con motivo y autor (persona o sistema). |
| III. Recuperable | **Cumple con atención.** La operación es durable, con arrendamiento y CAS, e idempotente por `(servicio, revisión)`; un resultado incierto se reintenta con la misma revisión sin multiplicar efectos. No crea recursos huérfanos. **Riesgo principal** (R7). |
| IV. Aislamiento por cátedra | **Cumple.** La clave pertenece a un servicio; el runner verifica `vmid`, nodo, pool, `resource_uuid` y nonce antes de escribir, de modo que un `vmid` reutilizado no recibe la clave anterior. |
| V–VI | No aplican a este alcance (sin cambios de vigencia ni de catálogo). Se revisarán en `/speckit-analyze`. |
| VII. Simplicidad | **Cumple.** Un dato nuevo para la persona (la clave pública), un bloque nuevo en el detalle y un botón «Cambiar clave». Usuario fijo `nap`, una clave por servicio, sin opciones hipotéticas. |
| Seguridad | La clave viaja por stdin del runner, nunca en `argv`; validación doble (portal y nodo); solo huellas en registros; `PasswordAuthentication no`, `PermitRootLogin no`. |

**Re-evaluación posterior al diseño**: sin violaciones. Se justifica abajo la única complejidad nueva (un protocolo de runner).

## Project Structure

### Documentation (this feature)

```text
specs/017-acceso-ssh-iaas-linux/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md
│   └── runner-iaas-access.md
├── checklists/requirements.md
└── tasks.md              # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── utils/ssh_keys.py                      # NUEVO: validar/normalizar/huella
│   ├── models/clave_acceso_servicio.py        # NUEVO
│   ├── schemas/pedido.py                      # +clave_ssh_publica en DatosSolicitud
│   ├── schemas/guest_runner.py                # +protocolo nap-iaas-access/1 (o módulo hermano)
│   ├── services/iaas_acceso_service.py        # NUEVO: registrar/reemplazar, operación, estado derivado
│   ├── services/service_access_service.py     # +bloque acceso_ssh (metodo sin cambios)
│   ├── services/admision_service.py           # clave → asignacion_snapshot
│   ├── services/orquestacion_service.py       # materializar fila; paso configure/probe en bootstrap IaaS; tipo acceso_ssh
│   ├── services/guest_runner_client.py        # transporte para el protocolo nuevo (mismo SSH)
│   └── routers/servicios.py                   # PUT /servicios/{id}/acceso-ssh
├── alembic/versions/…_claves_acceso_servicio.py
└── tests/…                                    # ver quickstart.md

infra/
├── runner/
│   ├── iaas_access.py                         # NUEVO: configure/probe (solo stdlib)
│   ├── nap_guest_runner.py                    # +despacho por protocolo (NO tocar node_executor.py)
│   └── tests/test_iaas_access.py              # NUEVO
└── applications/install.py                    # +iaas_access.py en SOURCES/ALLOWED

frontend/
├── src/components/NuevoPedidoModal.jsx        # campo «Clave pública SSH» (solo IaaS Linux)
├── src/components/AccesoServicio.jsx          # bloque SSH + estados
├── src/components/CambiarClaveSshModal.jsx    # NUEVO
└── tests/acceso-ssh.test.jsx                  # NUEVO

docs/infraestructura-laboratorio/              # runbook del ensayo real (resultado de quickstart)
```

**Structure Decision**: se extiende la estructura web existente y se agrega un módulo en el paquete de nodo. No se crea ningún proyecto nuevo.

## Orden de entrega sugerido (para `/speckit-tasks`)

1. **Base sin infraestructura**: `ssh_keys.py` + pruebas; esquema de pedido; modelo y migración.
2. **Runner**: `iaas_access.py` + despacho + `install.py` + pruebas (incluida la de `policy_digest` constante y la de «clave fuera de argv»).
3. **Portal**: servicio de acceso, materialización, paso `configure/probe` en el despliegue IaaS, bloque `acceso_ssh`. Con esto se entrega la historia 1.
4. **Reinicio y vida del servicio** (historia 2): `probe` al iniciar; no declarar utilizable sin confirmar.
5. **Operación `acceso_ssh` + `PUT`** (historia 3 y servicios existentes). Antes, leer completo `orquestacion_service.py` y `operaciones.py`.
6. **Frontend**: pedido, bloque de acceso, modal de cambio.
7. **Ensayo real** (quickstart) en pve91 y frt; documentar en el runbook.

Cada tramo deja el sistema funcionando y es demostrable; los tramos 1–3 + 6 son el MVP de la historia 1.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| La plantilla no trae `openssh-server` (R10) | Verificar el primer día; si falta, el fallo es explícito (`SSHD_UNAVAILABLE`) y se decide plantilla antes de seguir. |
| La operación durable nueva (R7) rompe la máquina de leases existente | Leer completo el orquestador antes de tasks; empezar por la prueba de idempotencia. |
| Tocar sin querer un archivo del `policy_digest` | Prueba automática que compara el digest; revisión de diff en el PR. |
| Una clave comprometida da `sudo` completo en el contenedor | Aceptado y documentado: LXC `unprivileged`, sin privilegios en el nodo; la red del IaaS no está aislada (limitación declarada en la spec). |
| El servicio IaaS no tiene aislamiento de red (R1) | Declarado; fuera de alcance. Recomendar feature aparte antes de abrirlo a más cátedras. |

## Complexity Tracking

| Violación / complejidad | Por qué hace falta | Alternativa más simple rechazada porque |
|---|---|---|
| Protocolo nuevo `nap-iaas-access/1` en el runner | Crear usuario, reemplazar clave y alcanzar servicios ya entregados exigen ejecutar dentro del invitado (Proxmox no lo permite por API). | `ssh-public-keys` de Proxmox solo sirve al crear y solo para `root`; reutilizar `nap-guest-runner/1` exige receta y `bundle` que el IaaS crudo no tiene. |
| Operación durable `acceso_ssh` | Un reemplazo es una operación contra infraestructura y debe ser recuperable (Principio III). | Ejecutarlo dentro de la petición HTTP dejaría estados ambiguos si el nodo no responde. |
