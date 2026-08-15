# Phase 0 — Research: Recuperación de Errores y Eliminación Lógica

**Feature**: `001-pedido-soft-delete-retry`
**Fecha**: 2026-08-07

Este documento resuelve las incógnitas técnicas detectadas al contrastar el spec con el código existente.

---

## R1. El VMID del intento fallido hoy NO se persiste

**Hallazgo (bloqueante para FR-004)**: En `backend/app/services/orquestacion_service.py:118`, el VMID se obtiene con `pve.get_next_vmid()` *dentro* del bloque `try`, y el registro `Servicio` (único lugar donde vive `proxmox_vmid`) se crea **después** de que `create_lxc` haya tenido éxito (línea ~150). Por lo tanto, cuando el despliegue falla, **no queda ningún VMID guardado en la base de datos**: no existe fila de `Servicio` y el `Pedido` no tiene columna para ello.

Sin persistir esa reserva, el requisito FR-004 ("reutilizar el VMID previamente asignado") es imposible de cumplir.

**Decision**: Agregar la columna `vmid_reservado` al modelo `Pedido`, escrita en el momento en que se obtiene el VMID (antes de llamar a `create_lxc`) y con `commit` propio, de modo que sobreviva al fallo.

**Rationale**: Es el cambio mínimo que hace verificable a FR-004. Mantiene `Servicio` como el registro de recursos *efectivamente desplegados* (semántica actual intacta) y usa `Pedido` como el registro de la *intención* de despliegue, que es donde naturalmente vive un intento fallido.

**Alternatives considered**:
- *Crear la fila `Servicio` en estado provisional antes de llamar a Proxmox*: sería más robusto ante fallos parciales, pero obliga a agregar un estado `PROVISIONING` al enum `EstadoServicio` y a auditar todos los sitios que asumen que un `Servicio` existente equivale a un contenedor real. Demasiada superficie para el alcance de este hito.
- *No reutilizar el VMID y pedir siempre uno nuevo*: más simple, pero contradice FR-004 y desperdicia VMIDs en clústeres con reintentos frecuentes.

---

## R2. Fallo parcial: contenedor creado pero pedido en ERROR

**Contexto**: Si `create_lxc` llega a crear el contenedor en Proxmox pero la respuesta se pierde (timeout de red, corte), el `except` marca el pedido en ERROR mientras el contenedor **sí existe** en el clúster. Un reintento ingenuo crearía un segundo contenedor duplicado consumiendo cuota real.

**Decision**: Antes de crear, el reintento consulta el clúster (`get_cluster_resources()`) para ver si `vmid_reservado` ya está ocupado:
- **Libre** → se reutiliza ese VMID (caso normal, FR-004).
- **Ocupado y el hostname coincide** con el esperado para ese pedido (`cat{catedra_id}-svc{pedido_id}`) → es un huérfano de nuestro propio fallo parcial: se **adopta** registrando el `Servicio` sobre el contenedor existente, sin crear uno nuevo.
- **Ocupado con otro hostname** → el VMID fue tomado por un tercero: se descarta la reserva y se pide un VMID nuevo (edge case del spec).

**Rationale**: Es lo que convierte el reintento en "pseudo-idempotente" tal como lo pidió el spec: repetirlo no multiplica contenedores. El hostname ya es determinístico (`_generar_hostname`), así que la identificación del huérfano no requiere estado adicional.

**Alternatives considered**:
- *Ignorar el caso y crear siempre*: deja contenedores huérfanos consumiendo recursos del clúster sin registro en la base — inaceptable en un entorno con cuotas por cátedra.
- *Borrar el huérfano y recrear*: destructivo y más lento, sin beneficio frente a adoptarlo.

---

## R3. Cómo excluir los registros dados de baja de los listados

**Decision**: Filtro explícito `.where(Modelo.deleted_at.is_(None))` en cada consulta, encapsulado en dos helpers reutilizables (`solo_activos(query, Modelo)` o equivalente) para evitar repetición.

**Rationale**: Los sitios de consulta afectados son pocos y conocidos (ver R4), el filtro queda visible y greppable en el código, y —crucialmente— no interfiere con las consultas de auditoría histórica que **deben** ver los registros dados de baja (FR-011).

**Alternatives considered**:
- *Filtro global vía evento `do_orm_execute` + `with_loader_criteria` de SQLAlchemy 2.0*: elegante y a prueba de olvidos, pero oculta filas de forma implícita en todo el sistema y obliga a un mecanismo de opt-out para el camino de auditoría. Magia riesgosa para un equipo chico; se descarta por el principio de que el borrado lógico nunca debe sorprender a quien lee el código.
- *Vistas de base de datos*: agrega una capa de esquema que Alembic tendría que versionar a mano.

---

## R4. Inventario de sitios de consulta a corregir

Relevado sobre el código actual; todo sitio que hoy asume "toda fila es una fila viva" debe filtrarse:

| Archivo | Línea aprox. | Consulta | Acción |
|---------|--------------|----------|--------|
| `routers/pedidos.py` | 32 | `select(Pedido)` (listado) | Excluir dados de baja |
| `routers/pedidos.py` | 63, 106 | `db.get(Pedido, ...)` | 404 si está dado de baja |
| `routers/servicios.py` | 25 | `select(Servicio)` (listado) | Excluir dados de baja |
| `routers/servicios.py` | 36, 103 | `db.get(Servicio, ...)` | 404 si está dado de baja |
| `routers/catedras.py` | 63 | Uso de recursos por cátedra | Excluir dados de baja (FR-012) |
| `routers/metricas.py` | 67, 91, 148, 165 | Servicios con métricas | Excluir dados de baja |
| `services/pedido_service.py` | 57 | `verificar_cuota` | Excluir dados de baja (FR-012) |
| `services/metricas_service.py` | 97 | Captura periódica de snapshots | Excluir dados de baja (no medir lo dado de baja) |

**Nota**: `db.get()` no acepta filtros; en esos sitios el chequeo es una condición explícita posterior (`if not obj or obj.deleted_at: 404`).

---

## R5. Corrección del desajuste de guarda entre máquina de estados y orquestador

**Contexto**: `pedido_service.TRANSICIONES_VALIDAS` permite `ERROR → EN_DESPLIEGUE` (línea 23), pero `orquestacion_service.desplegar_pedido()` exige `estado == APROBADO` (línea 88). El resultado es que la transición se puede ejecutar vía `PATCH /pedidos/{id}/estado` pero nada dispara el despliegue real: el pedido queda colgado en EN_DESPLIEGUE.

**Decision**: Extraer el cuerpo de aprovisionamiento a una función interna compartida `_ejecutar_despliegue(db, pedido, admin, node, storage)`, y dejar dos puntos de entrada que se diferencian **solo** en la validación de estado de entrada:
- `desplegar_pedido()` → exige `APROBADO`, transiciona a `EN_DESPLIEGUE`, delega.
- `reintentar_despliegue()` → exige `ERROR`, transiciona a `EN_DESPLIEGUE`, delega.

**Rationale**: Elimina la duplicación de la lógica de Proxmox (que es la parte frágil) y hace que el bug sea estructuralmente imposible: ambos caminos terminan en el mismo código de despliegue. `TRANSICIONES_VALIDAS` no necesita cambios.

**Alternatives considered**:
- *Relajar la guarda a `estado in (APROBADO, EN_DESPLIEGUE)`*: reabre el riesgo de disparar un despliegue sobre un pedido ya en curso (doble contenedor) y deja el reintento sin punto de entrada explícito, contra FR-001.
- *Un worker que barra pedidos colgados*: introduce ejecución en segundo plano, fuera del alcance de este hito.

---

## R6. Infraestructura de pruebas (no existe hoy)

**Contexto**: El repositorio no tiene ningún archivo `test_*.py` y `pytest` no figura en `backend/requirements.txt`. Los criterios de éxito del spec no son verificables sin ella.

**Decision**: Incorporar en este hito el mínimo andamiaje: `pytest`, `pytest-asyncio`, `httpx` y `aiosqlite`, con una base SQLite en memoria para las pruebas y un doble de prueba (fake) del cliente Proxmox inyectado por override de dependencias de FastAPI.

**Rationale**: La lógica central de este feature es precisamente el manejo de fallos de infraestructura, que es imposible de validar a mano de forma repetible sin poder simular que Proxmox falla. Bootstrapear pytest acá habilita además toda la sección 3 del `PLAN_TRABAJO.md`.

**Consideración**: `Pedido.parametros_extra` usa el tipo `JSON`, soportado por SQLite; no se detectaron tipos específicos de PostgreSQL que rompan bajo SQLite. Si apareciera alguno, la alternativa es levantar PostgreSQL en contenedor para las pruebas.

**Alternatives considered**:
- *Postergar las pruebas al hito de testing*: dejaría este feature —cuyo objetivo es la robustez ante fallos— sin ninguna evidencia de que efectivamente maneja los fallos.

---

## R7. Momento del `deleted_at` frente a la liberación del recurso real

**Decision**: Al dar de baja un `Servicio`, se intenta primero liberar el contenedor en Proxmox (comportamiento actual de `eliminar_servicio`); solo si esa operación tiene éxito se escribe `deleted_at`. Si Proxmox falla, se propaga el error y el registro **no** se marca (FR-010).

**Rationale**: Evita el peor escenario: un registro que dice "dado de baja" mientras el contenedor sigue vivo consumiendo recursos del clúster sin que nadie lo vea en los listados.

**Alternatives considered**:
- *Marcar primero y liberar después*: rápido para el usuario pero puede dejar recursos fantasma invisibles.
- *Marcar aunque falle, con bandera de "pendiente de liberación"*: requiere un proceso de reconciliación que no existe; se descarta por ahora.
