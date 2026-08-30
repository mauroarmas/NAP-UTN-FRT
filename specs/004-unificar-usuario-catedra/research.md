# Research: Unificación usuario–cátedra y control de recursos por aprobación

**Feature**: 004-unificar-usuario-catedra | **Fecha**: 2026-08-16

Fase 0 del plan. Cada sección resuelve una incógnita técnica con decisión, fundamento y
alternativas descartadas. Las incógnitas salen de contrastar la spec contra el código vigente.

---

## R1. No existe ejecución periódica en el sistema

**Incógnita**: la spec exige tres procesos que corren solos —expirar reservas (FR-018d), aplicar
vencimientos (FR-018k) y pausar por inactividad (FR-019)—, pero el repositorio no tiene ningún
planificador. El `lifespan` de [main.py:12](../../backend/app/main.py#L12) solo imprime mensajes, y
la única recolección de métricas que existe se dispara **a mano** desde un endpoint
([metricas.py:57](../../backend/app/routers/metricas.py#L57)).

**Decisión**: cada trabajo periódico se implementa como **tres piezas separadas**:

1. Una función de servicio pura en `app/services/`, que recibe `AsyncSession` y devuelve un
   resumen de lo actuado. No sabe nada de cómo fue invocada.
2. Un endpoint `POST` admin-only que la invoca, siguiendo el patrón que ya usa la recolección de
   métricas.
3. Un planificador **APScheduler** (`AsyncIOScheduler`) arrancado en el `lifespan` de la app, que
   llama a la misma función de servicio.

**Fundamento**: las pruebas ejercitan la función de servicio directamente, sin planificador ni
reloj real — que es la única forma de cumplir la compuerta de calidad de la constitución sin
volver las pruebas lentas o intermitentes. El endpoint manual da una vía de operación y depuración
que el equipo ya conoce. Y el planificador queda como una cáscara sin lógica: si falla, se degrada
a operación manual en lugar de romper la feature.

**Riesgo a mitigar**: APScheduler en el proceso de la app ejecuta el trabajo **una vez por worker**.
Con `uvicorn --workers N` los vencimientos se aplicarían N veces. Mitigación: un *lock* de
exclusión en base (una fila `job_locks` con `CHECK` de unicidad por nombre de trabajo y ventana),
tomado antes de ejecutar. Es más simple que introducir Celery/Redis y suficiente para el despliegue
real, que es de instancia única.

**Alternativas descartadas**:

- *Cron del sistema operativo golpeando el endpoint*: acopla el despliegue a configuración externa
  del host, invisible para el repositorio y difícil de reproducir en desarrollo.
- *Celery + Redis*: introduce dos servicios nuevos de infraestructura para tres trabajos periódicos
  triviales. Desproporcionado para el tamaño del sistema.
- *`asyncio.create_task` con un `while True: sleep(...)`*: es APScheduler mal hecho, sin manejo de
  errores, sin solapamiento controlado y sin observabilidad.

---

## R2. Atomicidad de la reserva: PostgreSQL en producción, SQLite en pruebas

**Incógnita**: FR-018c exige que verificar disponibilidad y crear la reserva sean indivisibles, y
que dos aprobaciones simultáneas no puedan comprometer la misma capacidad. La constitución v2.0.0
además obliga a cubrirlo con una prueba de concurrencia. Pero las pruebas corren sobre **SQLite en
memoria** ([conftest.py:30](../../backend/tests/conftest.py#L30)) y producción sobre PostgreSQL;
los mecanismos de bloqueo no son los mismos.

**Decisión**: dos capas complementarias, no una.

**Capa 1 — Exclusión mutua real (protege la integridad)**. Un ayudante
`bloqueo_capacidad(db)` en `app/services/capacidad_service.py`:

- En PostgreSQL ejecuta `SELECT pg_advisory_xact_lock(<clave fija>)`, que serializa la sección
  crítica y se libera solo al terminar la transacción.
- En SQLite es un no-op, porque el motor ya serializa las escrituras.

El dialecto se detecta con `db.bind.dialect.name`. Toda la lectura de capacidad comprometida y la
creación de la reserva ocurren dentro de ese bloqueo, en **una sola transacción**.

**Capa 2 — Token de capacidad (protege la decisión humana)**. La pantalla de aprobación recibe un
`capacidad_token`: el hash corto de la tupla de capacidad comprometida vigente. Al confirmar, el
cliente lo devuelve; el servidor recalcula y compara. Si difiere, responde **409** con los números
nuevos y no aprueba.

**Fundamento**: son dos problemas distintos que suelen confundirse. La capa 1 impide que dos
transacciones concurrentes lean el mismo saldo y ambas reserven — es corrupción de datos. La capa 2
impide que un administrador confirme una decisión que tomó mirando números viejos (la pestaña
abierta media hora, el otro admin que aprobó en el medio) — es una decisión mal informada, no una
condición de carrera. La capa 1 sola dejaría pasar la aprobación con datos viejos, solo que
correctamente serializada. La capa 2 sola no impide el solapamiento real.

Además, la capa 2 es exactamente lo que pide el escenario de aceptación 4 de la US3 ("recalcula la
capacidad y le pide confirmar sobre los valores vigentes") y es verificable en SQLite, donde el
bloqueo no hace nada.

**Alternativas descartadas**:

- *`SELECT ... FOR UPDATE` sobre las filas de pedidos*: no protege contra la inserción de una
  reserva nueva por otra transacción (no hay fila que bloquear todavía). Habría que bloquear una
  fila-centinela, que es un advisory lock con más ceremonia.
- *Nivel de aislamiento `SERIALIZABLE`*: correcto pero obliga a manejar reintentos por fallo de
  serialización en toda la aplicación, no solo acá.
- *Solo el token, sin bloqueo*: deja una ventana real entre el recálculo y el `INSERT`.
- *Una tabla `capacidad` con un contador*: duplica un estado que ya es derivable, y crea la
  posibilidad de que el contador y la realidad diverjan — el defecto exacto que el Principio III
  prohíbe.

---

## R3. Dónde vive la reserva

**Incógnita**: la spec introduce "Reserva de capacidad" como entidad (FR-018b a FR-018e). ¿Tabla
propia o estado derivado?

**Decisión**: **derivada del pedido**, sin tabla nueva. Un pedido en estado `APROBADO` sin servicio
desplegado **es** una reserva. Se agregan a `pedidos` las columnas del compromiso:
`reserva_vcpus`, `reserva_ram_mb`, `reserva_disk_gb`, `reserva_expira_at`.

**Fundamento**: FR-018e exige explícitamente que la reserva no se contabilice dos veces al
convertirse en consumo real. Con una tabla aparte hay dos fuentes de verdad que hay que mantener
sincronizadas —y la constitución (Principio III) prohíbe justamente la clase de divergencia donde
el registro y la realidad se separan. Derivándola, "convertir la reserva en consumo" no es una
operación: es simplemente que el pedido pasa a `ACTIVO` y el `Servicio` existe, y la consulta de
capacidad comprometida deja de contarlo como reserva y empieza a contarlo como despliegue. No hay
paso intermedio que pueda fallar a medias.

**Por qué se copian los valores en vez de leerlos del template**: el template puede editarse después
de la aprobación. La reserva tiene que ser un compromiso sobre números concretos, no una referencia
a números que pueden cambiar. Es el mismo criterio con el que `Pedido.vmid_reservado` ya persiste
el VMID en lugar de recalcularlo ([pedido.py:65](../../backend/app/models/pedido.py#L65)).

**Alternativas descartadas**:

- *Tabla `reservas` con FK al pedido*: doble contabilidad, riesgo de desincronización, y ninguna
  consulta se vuelve más simple.
- *Leer los recursos del template al calcular*: se rompe si alguien edita el template entre la
  aprobación y el despliegue.

---

## R4. El sistema como autor en el historial

**Incógnita**: `PedidoHistorial.usuario_id` es `NOT NULL`
([pedido.py:88](../../backend/app/models/pedido.py#L88)), pero el vencimiento, el pausado
automático y la expiración de reservas no tienen persona detrás. El Principio II (v2.0.0) ahora
exige que el sistema quede identificado como autor propio y prohíbe atribuirlo a una persona.

**Decisión**: `usuario_id` pasa a **nullable**; `NULL` significa "el sistema". Se agrega un
ayudante `autor_display(registro)` para la capa de presentación y se expone en el schema de
respuesta como `autor: "sistema"`.

**Fundamento**: es la migración más chica que satisface el principio, y `NULL` ya tiene la
semántica correcta ("no hay persona") sin inventar convenciones. Toda consulta de historial ya
tiene que hacer join opcional para mostrar el nombre.

**Alternativas descartadas**:

- *Un usuario centinela "sistema" en la tabla `usuarios`*: contamina el listado de usuarios, puede
  recibir login por error, y obliga a filtrarlo en cada consulta de personas. El costo se paga en
  todas partes para ahorrar una migración de nulabilidad en un solo lugar.
- *Una columna `actor_tipo` enum*: redundante con `usuario_id IS NULL`; dos campos que pueden
  contradecirse.

---

## R5. Los servicios no tienen historial

**Incógnita**: FR-029 (pausa/reactivación automática) y FR-018l (vencimiento) exigen registrar en
"el historial del servicio". Solo existe `pedidos_historial`; no hay equivalente para `servicios`.

**Decisión**: tabla nueva `servicios_historial`, con la misma forma que `pedidos_historial`
(`servicio_id`, `estado_anterior`, `estado_nuevo`, `comentario`, `usuario_id` nullable,
`created_at`), y de solo agregado.

**Fundamento**: registrar contra el pedido no sirve: `Servicio.pedido_id` es nullable
([servicio.py:31](../../backend/app/models/servicio.py#L31)), así que hay servicios sin pedido, y
además el ciclo de vida del servicio (encendido, apagado, pausa, vencimiento, renovación) es más
largo que el del pedido que lo originó. El Principio V exige que el rastro sobreviva; guardarlo en
una entidad que puede no existir lo incumple.

Se aprovecha para registrar también las acciones manuales de la feature 003 (encender/apagar/
reiniciar), que hoy no dejan rastro.

---

## R6. Detección de inactividad sobre las métricas existentes

**Incógnita**: FR-019 necesita "actividad observada durante una ventana"; FR-028 prohíbe
interpretar la falta de datos como inactividad. `MetricaSnapshot` ya guarda `cpu_usage_percent`,
`ram_usage_mb`, `net_in_bytes`, `net_out_bytes` y `timestamp`
([metrica.py:16-21](../../backend/app/models/metrica.py#L16-L21)), pero **nadie las recolecta
periódicamente** (R1): hoy solo hay datos si alguien golpeó el endpoint.

**Decisión**:

- La recolección de métricas pasa a ser el **cuarto trabajo periódico** del planificador de R1, con
  una cadencia de 15 minutos.
- Un servicio se considera inactivo si, **dentro de la ventana**, tiene **cobertura de datos
  suficiente** (al menos el 80% de los snapshots esperados) **y** todos ellos están por debajo del
  umbral de actividad.
- El umbral combina CPU y red: `cpu_usage_percent < 5` **y** el delta de `net_in_bytes +
  net_out_bytes` por debajo de un piso configurable. La RAM no se usa como señal.
- Si la cobertura es insuficiente, el servicio **no es candidato** y se registra el motivo.

**Fundamento**: exigir cobertura mínima es la traducción directa de FR-028 y del riesgo 6 de la
spec — es la diferencia entre "no lo usó nadie" y "no lo miramos". La RAM se descarta como señal
porque un proceso ocioso mantiene su memoria residente: un contenedor sin usar hace semanas puede
mostrar 300 MB estables y parecer activo. La red se incluye porque es lo que distingue a un
servidor que atiende pedidos de uno que solo respira.

**Nota de alcance**: al aplicarse el cambio no hay historial de métricas, así que **ningún** servicio
tendrá cobertura suficiente durante la primera ventana. Eso satisface FR-033 sin código especial:
la regla de cobertura ya protege a los servicios preexistentes.

---

## R7. "Pausar" se implementa como detener

**Incógnita**: cerrada en la spec (sesión de clarificación), se documenta acá la mecánica concreta.

**Decisión**: la pausa por inactividad invoca `stop_lxc`
([proxmox_client.py:48](../../backend/app/services/proxmox_client.py#L48)) y deja
`Servicio.estado = PAUSED`. La reactivación invoca `start_lxc`.

**Fundamento**: el cliente de Proxmox del proyecto **no expone** suspensión — solo `start_lxc`,
`stop_lxc` y `reboot_lxc`. Y aunque se agregara, la suspensión de un contenedor depende de CRIU,
que Proxmox documenta como experimental y que falla ante conexiones abiertas. Detener libera CPU y
RAM por completo, el `rootfs` es persistente y el arranque es de segundos.

**Consecuencia a manejar**: `EstadoServicio.PAUSED` hoy solo se asigna **leyendo** el estado de
Proxmox ([orquestacion_service.py:30-31](../../backend/app/services/orquestacion_service.py#L30-L31)),
donde `"paused"`/`"suspended"` de Proxmox mapean a `PAUSED`. Como ahora la pausa del portal deja el
contenedor **detenido**, Proxmox reportará `"stopped"` y `sincronizar_estados` sobrescribiría
`PAUSED` por `STOPPED`, borrando la distinción. Se resuelve con `Servicio.pausado_auto_at`: la
sincronización respeta `PAUSED` mientras esa marca esté puesta. La distinción entre "lo apagó la
cátedra" y "lo pausó el sistema" vive en el portal, no en Proxmox — es exactamente el tipo de
mapeo que el Principio I pone del lado del portal.

---

## R8. Migración a titular único

**Incógnita**: hoy `Usuario.catedra_id` apunta a una cátedra
([usuario.py:28](../../backend/app/models/usuario.py#L28)) y `Catedra.usuarios` es una lista
([catedra.py:22](../../backend/app/models/catedra.py#L22)): N usuarios por cátedra. El modelo nuevo
invierte la relación y exige titular único (FR-001b), con constancia de quién pierde acceso
(FR-034).

**Decisión**: se invierte la dirección de la relación.

- Se agrega `catedras.titular_id` → `usuarios.id`, nullable durante la migración.
- El titular de cada cátedra se elige de forma **determinista**: el usuario de menor `id` entre los
  que hoy la tienen asignada. Sin heurísticas de "actividad reciente".
- Los desplazados se vuelcan a una tabla de bitácora `migracion_004_accesos_perdidos`
  (`usuario_id`, `username`, `catedra_id`, `catedra_nombre`, `migrado_at`), consultable desde un
  endpoint admin.
- Se elimina `usuarios.catedra_id` en una migración **posterior**, no en la misma.

**Fundamento**: el criterio determinista es auditable y reproducible; cualquier regla "inteligente"
(el que creó más pedidos, el que entró último) produce resultados que nadie puede verificar y que
cambian según cuándo se corra. La bitácora es la traducción literal de FR-034: el requisito no es
resolver el conflicto automáticamente, es que nadie descubra que perdió acceso al no poder entrar.

Separar el `DROP COLUMN` en una migración posterior deja una ventana en la que ambos esquemas
coexisten y el `downgrade` es posible sin pérdida de datos.

**Alternativas descartadas**:

- *Tabla de asociación N:M*: contradice FR-001b, que ya fue decidido.
- *Elegir titular por actividad*: no auditable, no reproducible.
- *Bloquear la migración si hay cátedras compartidas*: convierte un caso conocido y manejable en un
  despliegue fallido.

---

## R9. Los avisos se derivan, no se almacenan

**Incógnita**: FR-020 (aviso previo a la pausa) y FR-018h (aviso previo al vencimiento) exigen
avisar dentro del portal. ¿Hace falta una tabla de notificaciones?

**Decisión**: no. Los avisos se **derivan** del estado del servicio en cada consulta:
`vence_at`, `pausa_programada_at` y el momento actual alcanzan para que el panel muestre "vence en
3 días" o "se pausará el viernes si nadie lo usa". Se persisten únicamente las marcas
`aviso_vencimiento_at` y `aviso_pausa_at`, que registran **cuándo** el sistema decidió avisar —
necesarias para el período de gracia (FR-020) y para probar FR-021.

**Fundamento**: la spec ubica el aviso dentro del portal y deja el correo fuera de alcance. Un
aviso derivado no puede quedar desincronizado del hecho que lo motiva, no requiere limpieza, y no
agrega una entidad que habría que mantener. Si más adelante entra el correo electrónico, la tabla
de notificaciones se agrega entonces, cuando exista algo que efectivamente haya que despachar y
cuyo envío haya que registrar.

---

## R10. Alcance multi-cátedra en las dependencias de autorización

**Incógnita**: el aislamiento entero descansa hoy en comparar contra `current_user.catedra_id`. Hay
al menos seis puntos: [pedidos.py:42](../../backend/app/routers/pedidos.py#L42) y
[:85](../../backend/app/routers/pedidos.py#L85),
[servicios.py:54](../../backend/app/routers/servicios.py#L54),
[metricas.py:94](../../backend/app/routers/metricas.py#L94) y
[:153](../../backend/app/routers/metricas.py#L153),
[orquestacion_service.py:49](../../backend/app/services/orquestacion_service.py#L49),
[catedras.py:161](../../backend/app/routers/catedras.py#L161) y
[:176](../../backend/app/routers/catedras.py#L176). El riesgo 10 de la spec advierte que cualquier
punto omitido es una fuga entre cátedras.

**Decisión**: se centraliza en `app/services/acceso_service.py` con dos funciones, y se **prohíbe**
la comparación directa fuera de ahí:

- `catedras_visibles(db, usuario) -> set[int]` — el conjunto de ids que la persona puede ver
  (todas, si es admin).
- `requiere_acceso_catedra(db, usuario, catedra_id)` — lanza 403 si no corresponde.

Cada router pasa de `where(X.catedra_id == current_user.catedra_id)` a
`where(X.catedra_id.in_(await catedras_visibles(db, usuario)))`.

**Verificación**: como el cambio es mecánico y de superficie amplia, se agrega una prueba de
regresión que, con un usuario de dos cátedras y una tercera ajena poblada, recorre **todos** los
endpoints de listado y verifica que ninguno devuelva recursos de la cátedra ajena. Es la única
forma de que "no me olvidé de ninguno" sea una afirmación verificable y no una promesa.

---

## R11. La renovación es un pedido

**Incógnita**: FR-018i exige que la renovación atraviese el mismo circuito de aprobación que un
pedido nuevo, y FR-018j que no recree el servicio.

**Decisión**: `Pedido` gana `tipo: TipoPedido = {ALTA, RENOVACION}` y `servicio_id` nullable (el
servicio que se renueva). La máquina de estados es **la misma**; lo que cambia es el ejecutor de la
transición a `ACTIVO`: en `ALTA` despliega un contenedor nuevo, en `RENOVACION` solo corre
`Servicio.vence_at`.

**Fundamento**: reutilizar la máquina de estados es lo que hace que "el mismo circuito de
aprobación" sea literal y no una copia parecida. El Principio II exige que toda transición tenga un
ejecutor real; acá hay dos ejecutores para la misma transición, seleccionados por el tipo de
pedido, ambos concretos.

**Consecuencia sobre la reserva**: una renovación **no** reserva capacidad nueva — el servicio ya
está desplegado y ya cuenta como consumo. Sus columnas de reserva quedan en cero. Contarla sería
justamente la doble contabilidad que FR-018e prohíbe.

---

## R12. El buscador de cátedras en el alta de usuario

**Incógnita**: FR-035b pide un buscador con marcado múltiple "sin ensuciar la UI". El formulario
actual usa un `<select>` de cátedra única
([Usuarios.jsx:69](../../frontend/src/pages/Usuarios.jsx#L69)) y el proyecto no tiene librería de
componentes.

**Decisión**: componente propio `SelectorCatedras`, sin dependencias nuevas:

- Un campo de texto que filtra por `nombre` (insensible a mayúsculas y acentos).
- La lista filtrada con casilla de verificación por fila, altura máxima acotada con scroll interno.
- Las cátedras ya tomadas se muestran deshabilitadas con su titular al lado (FR-035c) — visibles,
  no ocultas, para que se entienda por qué no se pueden elegir.
- Las seleccionadas se listan como fichas removibles arriba del campo, así el estado se ve sin
  scrollear la lista.
- El filtrado es en cliente sobre el listado que la pantalla ya trae.

**Fundamento**: la escala real es de decenas de cátedras, no miles; traer el listado completo y
filtrar en memoria evita un endpoint nuevo y el retardo de teclear contra la red. El edge case del
buscador con 200 cátedras queda cubierto: filtrar 200 filas en memoria es instantáneo. Si el número
creciera un orden de magnitud, el cambio a filtrado en servidor es local al componente.

**Alternativas descartadas**:

- *Traer una librería de multiselect*: una dependencia nueva y un estilo ajeno al resto del portal
  para un caso que se resuelve con un input y una lista.
- *Endpoint de búsqueda con debounce*: complejidad de red sin beneficio a esta escala.

---

## Resumen de decisiones

| # | Incógnita | Decisión |
|---|---|---|
| R1 | Sin planificador | Servicio puro + endpoint admin + APScheduler en `lifespan`, con lock en base |
| R2 | Atomicidad PG/SQLite | Advisory lock (no-op en SQLite) **más** token de capacidad con 409 |
| R3 | Dónde vive la reserva | Derivada del pedido aprobado; columnas de compromiso en `pedidos` |
| R4 | Autor sistema | `usuario_id` nullable; `NULL` = sistema |
| R5 | Historial de servicio | Tabla nueva `servicios_historial`, de solo agregado |
| R6 | Detección de inactividad | Cobertura mínima de datos + umbral de CPU y red; RAM descartada |
| R7 | Pausar | `stop_lxc`; `pausado_auto_at` protege el estado de la sincronización |
| R8 | Titular único | Menor `id` como titular; bitácora de desplazados; `DROP` diferido |
| R9 | Avisos | Derivados del estado; solo se persiste cuándo se avisó |
| R10 | Multi-cátedra | `acceso_service` centralizado + prueba de regresión sobre todos los listados |
| R11 | Renovación | Tipo de pedido; misma máquina de estados, distinto ejecutor; no reserva |
| R12 | Buscador de cátedras | Componente propio, filtrado en cliente, sin dependencias nuevas |
