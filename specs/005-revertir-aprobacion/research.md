# Research: Revertir una aprobación antes del despliegue

**Feature**: 005-revertir-aprobacion | **Fecha**: 2026-08-30

Resuelve las decisiones que la spec dejó abiertas y las que aparecieron al inspeccionar el código.
Cada una registra qué se decidió, por qué, y qué se descartó.

---

## R1 — Cómo se habilita al administrador a ejecutar `APROBADO → RECHAZADO`

**El problema**: la transición ya existe y es válida, pero está en `TRANSICIONES_SISTEMA`, el conjunto
que `cambiar_estado` usa para rechazar con 409 cualquier intento humano. Fue puesta ahí a propósito
en la feature 004: el vencimiento de reservas necesitaba una forma legítima de cambiar el estado, y
se quiso evitar que alguien lo hiciera a mano y dejara la reserva sin liberar.

**Decisión**: `TRANSICIONES_SISTEMA` deja de ser "solo el sistema" y pasa a significar **"no se
alcanza cambiando el estado a mano"**. La reversión se expone como una **operación con nombre propio**
—igual que aprobar, rechazar o reintentar—, no como un cambio de estado genérico. El endpoint
`PATCH /pedidos/{id}/estado` sigue rechazando la transición.

**Rationale**: el peligro que motivó la restricción no era que una persona decidiera revertir; era
que alguien moviera el estado sin liberar la reserva, dejando capacidad huérfana. Esa preocupación se
resuelve mejor con una operación que hace las dos cosas juntas que con una prohibición que deja al
administrador sin salida.

El Principio II lo admite explícitamente: *"El autor de una transición puede ser una persona o el
propio sistema"*. Lo que exige es que toda transición pase por la función central y quede en el
historial con su autor — cosas que esta operación cumple.

**Alternativas descartadas**:

- *Sacar la transición de `TRANSICIONES_SISTEMA`*: reabriría el cambio de estado a mano por
  `PATCH /estado`, que es exactamente el camino que dejaría la reserva sin liberar.
- *Un flag `origen_sistema=True` desde el endpoint humano*: haría que el historial atribuyera al
  sistema una decisión que tomó una persona. Contradice el Principio II, que prohíbe atribuir mal una
  transición.

---

## R2 — Dónde vive la liberación de la reserva

**Decisión**: se extrae de `expirar_reservas` una función `liberar_reserva(pedido)` en
`capacidad_service`, que pone en cero los tres campos y limpia `reserva_expira_at`. La usan los dos
caminos: el vencimiento automático y la reversión humana.

**Rationale**: hoy esa lógica está incrustada en el bucle de `expirar_reservas`. Duplicarla en la
reversión crearía dos definiciones de "liberar una reserva" que pueden divergir — y divergir acá
significa capacidad fantasma. Una sola función, dos autores.

Conviene además recordar por qué esto es tan barato: **la reserva no es una tabla**. Es un estado
derivado —un pedido aprobado, de tipo alta, sin servicio, con la reserva no vencida—, según
`reservas_vigentes_where`. Liberar es dejar de cumplir esa condición. No hay fila que borrar ni saldo
que recalcular: el cálculo de capacidad deja de contarlo solo.

**Alternativas descartadas**:

- *Llamar a `expirar_reservas` desde la reversión*: recorre todos los pedidos vencidos, no el que se
  quiere revertir, y registraría al sistema como autor.
- *Que el endpoint ponga los campos en cero directamente*: es la duplicación que se quiere evitar.

---

## R3 — Atomicidad y concurrencia (FR-004, FR-005)

**Decisión**: la reversión ocurre entera dentro de `bloqueo_capacidad(db)`, el mismo contexto que ya
usa la aprobación. Dentro del bloqueo se relee el pedido y se verifica que siga en `APROBADO`; si no
lo está, la operación se rechaza sin tocar nada.

**Rationale**: es el mismo mecanismo que la feature 004 usa para que dos aprobaciones simultáneas no
resuelvan sobre el mismo saldo. En PostgreSQL toma un advisory lock de transacción; el lock se libera
al terminar la transacción, así que el cambio de estado y la liberación quedan indivisibles por
construcción (FR-004).

Para la concurrencia (FR-005) el bloqueo serializa, y la **verificación de estado dentro del bloqueo**
es lo que impide la doble liberación: la segunda reversión encuentra el pedido ya en `RECHAZADO`, que
no es un estado desde el que se pueda revertir, y falla con un conflicto explícito. Sin esa
verificación adentro, dos reversiones podrían pasar el chequeo de estado antes de que ninguna
escribiera, y liberar dos veces.

Es la misma estructura que el `capacidad_token` de la aprobación, con una diferencia: allá el
problema es decidir sobre números viejos, y acá es actuar dos veces sobre el mismo pedido. Por eso no
hace falta token: alcanza con releer el estado bajo el lock.

**Alternativas descartadas**:

- *Confiar en el `UPDATE ... WHERE estado = 'APROBADO'`*: funcionaría para la fila, pero la operación
  también escribe historial, y sin bloqueo el conteo de capacidad podría leerse entre medio.
- *Exigir `capacidad_token` como en la aprobación*: el token protege contra decidir sobre un saldo
  desactualizado. Revertir **libera**: no hay decisión que tomar contra el saldo, y pedirlo sería
  fricción sin beneficio.

---

## R4 — Cómo se distingue la reversión del rechazo y del vencimiento (FR-009)

**El problema**: los tres terminan en `RECHAZADO`. Sin distinción, el historial no permite reconstruir
si hubo capacidad comprometida y por cuánto tiempo, que es lo que el Principio V exige poder
responder.

**Decisión**: se distinguen por **el par (autor, motivo)** que ya viven en la entrada de historial,
sin agregar campos ni estados:

| Situación | Autor en el historial | Estado anterior | Motivo |
|---|---|---|---|
| Rechazo original | persona | `SOLICITADO` | el que escribió quien rechazó |
| **Reversión de aprobación** | **persona** | **`APROBADO`** | **el que escribió quien revirtió** |
| Vencimiento de reserva | sistema (`usuario_id` nulo) | `APROBADO` | generado por el sistema |

El **estado anterior** separa el rechazo original de los otros dos, y el **autor** separa la reversión
del vencimiento. Ambos datos ya se registran en cada entrada.

Además, `motivo_rechazo` del pedido se completa con un texto que nombra la situación —de modo que la
cátedra lea "se revirtió la aprobación" y no un "rechazado" a secas—, y la entrada de la aprobación
original permanece intacta, que es lo que hace legible la secuencia completa.

**Rationale**: agregar un estado `REVERTIDO` obligaría a revisar toda la máquina de estados, los
filtros de listado, la contabilidad de capacidad y el frontend, para expresar algo que los datos
existentes ya expresan. La spec (FR-009) pide que se puedan **distinguir**, no que tengan estados
distintos.

**Alternativas descartadas**:

- *Un estado `REVERTIDO` propio*: cambio grande para una distinción que ya es derivable. Además
  obligaría a decidir qué pasa con `reservas_vigentes_where`, que hoy filtra por `APROBADO`.
- *Un campo booleano `fue_revertido`*: una segunda fuente de verdad sobre algo que el historial ya
  dice, con el riesgo de que diverjan.

---

## R5 — Qué pasa si el despliegue ya empezó (FR-006)

**Decisión**: se rechaza con un conflicto explícito que nombra la vía correcta: dar de baja el
servicio una vez que exista. La verificación es el estado del pedido — solo `APROBADO` es reversible;
`EN_DESPLIEGUE`, `ACTIVO` y `ERROR` no lo son.

**Rationale**: en cuanto el aprovisionamiento empezó a tocar la infraestructura, la vuelta atrás deja
de ser una decisión administrativa y pasa a ser una baja de servicio, que ya tiene su propio camino
(`DELETE /servicios/{id}`) y su propia lógica de liberación en Proxmox. Mezclarlas metería a la
reversión en el negocio de destruir contenedores.

El caso `ERROR` merece mención: un pedido cuyo despliegue falló **conserva su reserva y su VMID
reservado** para poder reintentarse. Revertirlo desde ahí sería útil, pero es una decisión distinta
—implica decidir qué pasa con el VMID reservado y con un contenedor que puede haber quedado a medias—
y la spec no la cubre. Queda fuera de alcance, anotado acá para que no se lea como olvido.

**Alternativas descartadas**:

- *Permitir revertir desde `ERROR`*: alcance no especificado; ver arriba.
- *Permitir revertir desde `EN_DESPLIEGUE` cancelando la tarea de Proxmox*: cancelar una tarea en
  vuelo deja el clúster en un estado que nadie puede predecir.

---

## R6 — La reserva ya vencida sola (FR-014)

**Decisión**: si el trabajo periódico se adelantó, el pedido ya está en `RECHAZADO` y la reversión
falla por la misma verificación de estado de R3. El mensaje distingue este caso: no dice "transición
inválida" sino que la reserva ya se liberó sola y no hay nada que revertir.

**Rationale**: es la misma condición técnica que una doble reversión, pero para la persona son
situaciones distintas y el mensaje tiene que reflejarlo. Un "transición inválida" ante algo que el
sistema hizo por su cuenta se lee como una falla del portal.

Se detecta mirando la última entrada del historial: si la transición a `RECHAZADO` la ejecutó el
sistema, fue vencimiento; si la ejecutó una persona, ya lo revirtió alguien.

---

## R7 — Renovaciones (FR-013)

**Decisión**: revertir la aprobación de una renovación no toca el servicio que se renovaba. Conserva
su `vence_at` anterior y su estado.

**Rationale**: sale gratis por cómo está construido. Una renovación aprobada **no reserva capacidad**
—`aprobar_pedido` le asigna costo cero, porque el servicio ya cuenta como consumo— y el `vence_at` no
se mueve hasta que se **ejecuta** la renovación, no al aprobarla. Revertir antes de ejecutar deja al
servicio exactamente como estaba.

Lo único que hay que cuidar es no "liberar" una reserva que vale cero como si fuera algo: la
liberación es idempotente sobre ceros, así que no hay caso especial.

---

## R8 — Qué ve la cátedra (FR-010, FR-011)

**Decisión**: la cátedra ve el pedido con el motivo que escribió el administrador, y el portal lo
presenta como una aprobación revertida, no como un rechazo. Puede volver a pedir el mismo recurso sin
ninguna restricción.

**Rationale**: un pedido que estaba aprobado y deja de estarlo en silencio es indistinguible de una
falla del portal. La cátedra pierde la confianza en los estados que el sistema le muestra, que es
justamente lo que la máquina de estados existe para sostener.

Sobre no bloquear el pedido nuevo: la reversión no es una sanción. Lo más común es que el pedido se
rehaga cuando haya capacidad, y bloquearlo castigaría a quien no cometió el error. No hace falta
trabajo para conseguirlo: `crear_pedido` no mira pedidos anteriores.

**Sobre el aviso**: la cátedra se entera por el mismo canal por el que ya sigue sus pedidos. Si más
adelante se suma el correo institucional que el cliente ofreció en la reunión del 2026-08-25, esta
notificación es candidata natural, pero la feature no depende de eso.

---

## Resumen de decisiones

| Id | Decisión | Impacto |
|---|---|---|
| R1 | Operación con nombre propio; `PATCH /estado` sigue cerrado | Sin transiciones nuevas |
| R2 | `liberar_reserva()` extraída y compartida con el vencimiento | Evita dos definiciones |
| R3 | Todo dentro de `bloqueo_capacidad` + relectura del estado | Compuerta de concurrencia |
| R4 | Se distingue por (autor, estado anterior), sin estados ni campos nuevos | Sin migración |
| R5 | Solo `APROBADO` es reversible; `ERROR` queda fuera de alcance | Anotado explícitamente |
| R6 | La reserva ya vencida da un mensaje propio, no "transición inválida" | Detalle de mensaje |
| R7 | Las renovaciones salen gratis: no reservan y no mueven `vence_at` | Sin trabajo |
| R8 | La cátedra ve la reversión como tal y puede volver a pedir | Frontend |

**Ningún `NEEDS CLARIFICATION` queda abierto.**
