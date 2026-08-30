# Research: Retirar y corregir usuarios, cátedras y plantillas

**Feature**: 006-ciclo-vida-entidades | **Fecha**: 2026-08-30

Este documento resuelve las decisiones que la spec dejó deliberadamente abiertas y las que
aparecieron al inspeccionar el código. Cada una registra qué se decidió, por qué, y qué se descartó.

---

## R1 — Cómo se retira una plantilla: campo nuevo o el `activo` que ya existe

**Decisión**: se reutiliza el campo `activo` que `RecursoTemplate` ya tiene. Retirar una plantilla es
ponerlo en `false`. No se agrega ningún campo ni tabla.

**Rationale**: el campo existe y **ya está cableado en los dos lugares que importan**:

- `listar_templates` filtra `activo == True`, así que una plantilla retirada desaparece del catálogo
  sin tocar esa consulta (FR-005, primera mitad).
- `crear_pedido` rechaza plantillas inactivas con un 404 (`pedido_service.py:100`), así que ya es
  imposible pedir una retirada (FR-005, segunda mitad).
- `obtener_template` **no** filtra por `activo`, así que un pedido histórico que la referencia la
  sigue resolviendo (FR-006).

Es decir: el comportamiento que la spec pide ya está implementado; lo único que falta es una forma de
poner el campo en `false` desde el portal. Agregar un concepto nuevo de "retirada" duplicaría un
estado que ya existe y obligaría a revisar esos tres lugares.

**Alternativas descartadas**:

- *Campo `retirada_at` con fecha*: aportaría "cuándo se retiró", que nadie pidió, a cambio de una
  migración y de dos fuentes de verdad sobre lo mismo.
- *Borrado físico de plantillas*: imposible sin romper los pedidos y servicios que la referencian, y
  contrario al Principio V.

---

## R2 — Editar una plantilla que tiene un pedido aprobado sin desplegar

**Es la única decisión de esta feature que toca la contabilidad de capacidad**, y por eso se resuelve
acá y no en la implementación.

**El problema**: la aprobación de un pedido **reserva** capacidad calculada sobre los valores de la
plantilla en ese momento (`capacidad_service.costo_de(template)`, guardado en
`pedido.reserva_vcpus/ram_mb/disk_gb`). Si la plantilla se edita después, y el despliegue leyera los
valores nuevos, el servicio consumiría algo distinto de lo que se reservó. La capacidad comprometida
y la real quedarían en desacuerdo — exactamente el defecto que la feature 004 vino a cerrar.

**Decisión**: **el pedido aprobado se despliega con los valores que se le reservaron, no con los de
la plantilla editada.** La reserva es el contrato; la plantilla solo define el punto de partida al
crear el pedido.

**Rationale**: es lo que ya sostiene el Principio IV. La reserva existe precisamente porque entre
decidir y materializar hay una ventana en la que las cosas cambian, y el sistema no puede resolver
sobre números que ya no valen. Un pedido aprobado tiene sus tres números guardados en la fila; usarlos
es tanto lo más correcto como lo más simple. Además evita el escenario perverso de que editar una
plantilla sobrecomprometa el clúster de forma retroactiva y silenciosa, sin que nadie haya aprobado
nada nuevo.

**Verificado el 2026-08-30: hoy el despliegue NO hace esto.** `orquestacion_service.py:203-205` arma
la configuración del contenedor con `template.default_vcpus`, `template.default_ram_mb` y
`template.default_disk_gb`, y las líneas 362-364 registran el servicio con esos mismos valores. La
reserva guardada en el pedido no se usa al desplegar.

Esto convierte a R2 en **trabajo obligatorio de esta feature, no en una precaución**. Hoy el
desacople es imposible porque las plantillas no se pueden editar; en cuanto se agregue la edición
—que es el objeto de la US1— pasa a ser alcanzable:

1. La cátedra pide un servicio de 1 vCPU. El administrador lo aprueba y el sistema reserva 1 vCPU.
2. El administrador corrige la plantilla y la deja en 4 vCPU.
3. El pedido se despliega **con 4 vCPU**, habiendo reservado 1.
4. El clúster queda sobrecomprometido en 3 vCPU sin que nadie haya aprobado nada, y sin rastro.

Es decir: implementar la US1 sin corregir el origen de los valores **introduce** una fuga de
capacidad silenciosa. Por eso el despliegue debe pasar a leer `pedido.reserva_*` como parte de esta
feature, con prueba dedicada al escenario "la plantilla cambia entre la aprobación y el despliegue".

Para pedidos aprobados **antes** de este cambio, cuya reserva ya está guardada, los valores coinciden
con los de la plantilla vigente al aprobar, así que la corrección no altera su comportamiento.

**Alternativas descartadas**:

- *Desplegar con los valores nuevos*: rompe la correspondencia entre lo reservado y lo usado.
- *Impedir editar una plantilla con pedidos aprobados pendientes*: convierte un pedido pendiente en
  un candado sobre el catálogo, y como la reserva dura 24 h, el administrador tendría que esperar sin
  poder arreglar la plantilla rota. Es justo el escenario que motivó la feature.
- *Re-evaluar la capacidad de los pedidos afectados al editar*: sería una re-aprobación automática
  sin persona que decida, contra el espíritu del Principio IV.

**Qué ve el administrador**: al editar una plantilla con pedidos aprobados pendientes, el portal
avisa cuántos son y que se desplegarán con los valores que ya tienen reservados. Es información, no
un bloqueo (FR-003).

---

## R3 — Retirar una persona: baja lógica y qué hacer con la relación de pedidos

**Decisión**: `DELETE /usuarios/{id}` pasa a ser una **baja lógica**: pone `activo = False` y
conserva la fila. El borrado físico se conserva **solo** para cuentas sin historial (sin pedidos y
sin cátedras a cargo), donde no hay nada que preservar.

Además, la relación `Usuario.pedidos` se marca explícitamente como `passive_deletes` / sin cascada de
anulación, para que ningún camino futuro vuelva a intentar dejar un pedido sin solicitante.

**Rationale**: el Principio V dice que el historial no se destruye y que el consumo por cátedra debe
seguir siendo reconstruible. La autoría de un pedido es parte de eso. Hoy el borrado es físico
(`db.delete(usuario)`) y, como `pedidos.solicitante_id` es NOT NULL, SQLAlchemy intenta anularlo y la
base lo rechaza: de ahí el 500. El error no es un accidente sino la base defendiendo el historial.

Mantener el borrado real para cuentas vírgenes evita acumular basura de cuentas mal tipeadas, sin
costo para el historial: si no hay pedidos ni cátedras, no hay nada que reconstruir.

**Por qué el verbo sigue siendo `DELETE`**: cambiar la semántica del endpoint existente conserva el
contrato para el frontend, que ya llama `deleteUsuario`. El portal ya usa "dar de baja" con este mismo
sentido en pedidos y servicios (borrado lógico de la feature 001), así que el vocabulario es
consistente. La respuesta pasa de `204 No Content` a `200` con el estado resultante, para que la
interfaz pueda distinguir "se desactivó" de "se borró de verdad".

**Alternativas descartadas**:

- *Devolver 409 y exigir que el administrador desactive por `PATCH`*: técnicamente correcto pero
  obliga a la persona a saber de antemano si la cuenta tiene historial, que es información que no
  tiene a mano. FR-003 de la US2 pide explícitamente que no tenga que saberlo.
- *Cascada que borre los pedidos de la persona*: destruye historial de la **cátedra**, que no es de
  la persona. Directamente contrario al Principio V.
- *Reasignar los pedidos a un usuario "anónimo"*: falsea la autoría.

---

## R4 — Los guards del retiro y el del último administrador

**Decisión**: el retiro de una persona aplica, en este orden, tres verificaciones:

1. **No es uno mismo** (ya existe).
2. **No es el último administrador activo** (nuevo, FR-013), cuando la persona tiene rol
   administrador.
3. **No tiene cátedras a cargo** (existe hoy solo en `PATCH`; se extiende a `DELETE`).

**Rationale**: hay una asimetría preexistente que esta feature cierra. Desactivar por `PATCH` está
protegido por el guard de cátedras a cargo, pero borrar por `DELETE` no tiene ese guard: alguien
podía eliminar a un titular por una puerta y no por la otra. Que `DELETE` pase a ser una baja lógica
hace que las dos puertas lleven al mismo lugar, así que deben custodiarse igual.

La protección del último administrador no existe hoy y su ausencia es un riesgo real: el sistema
puede quedarse sin ninguna cuenta capaz de administrar, y no hay forma de recuperarse desde el portal.
Se cuenta sobre administradores **activos**, no sobre filas: una cuenta dada de baja no salva al
sistema.

**Alternativas descartadas**:

- *Solo proteger contra desactivarse a uno mismo*: no alcanza. Un administrador puede desactivar a
  otro y quedar como único, y después ser desactivado por... nadie, porque ya no hay quien lo haga.
  Pero sí puede quedar inactivo por otras vías.

---

## R5 — Cómo se corrige el mensaje de bloqueo por cátedras a cargo

**Decisión**: se corrige **el texto**, no el bloqueo ni la consulta. El mensaje pasa a nombrar
únicamente la salida que funciona: reasignar el titular. Se elimina la sugerencia de dar la cátedra
de baja.

**Rationale**: se verificó en el entorno real que dar la cátedra de baja **no** destraba la
operación, y se verificó por qué: `catedras_de` (`services/usuario_service.py:24`) busca por
`titular_id` sin mirar `activa`. La tentación es "arreglar" la consulta filtrando por `activa`, pero
eso sería peor: **desactivar una cátedra no detiene sus servicios** — `PATCH /catedras/{id}` con
`activa=false` solo pide confirmación cuando hay servicios vigentes, y los deja corriendo. Una
cátedra inactiva puede seguir consumiendo recursos reales, así que sigue necesitando responsable. El
guard tiene razón; el consejo, no.

Esto es lo que FR-017 fija explícitamente para que nadie lo "optimice" más adelante.

**Alternativas descartadas**:

- *Filtrar `catedras_de` por `activa`*: permitiría desactivar al titular de una cátedra dada de baja
  que todavía tiene contenedores corriendo. Cambia un mensaje confuso por un agujero real.
- *Ofrecer reasignación automática al administrador que ejecuta la acción*: decide por la persona
  algo que tiene consecuencias de responsabilidad. La spec pide indicar la salida, no tomarla.

---

## R6 — Qué listados ocultan a las personas retiradas

**Decisión**: `GET /usuarios/` pasa a devolver solo las personas activas por defecto, y acepta un
parámetro para incluir las retiradas. El detalle por id (`GET /usuarios/{id}`) sigue devolviendo a
cualquiera, activa o no.

**Rationale**: es exactamente el criterio que el Principio V ya fija para pedidos y servicios ("los
registros dados de baja MUST quedar excluidos de los listados operativos por defecto, sin que eso
implique su desaparición"). Aplicarlo a personas es consistencia, no invención. El detalle por id
tiene que seguir resolviendo para que el historial de un pedido pueda mostrar quién lo pidió aunque
esa persona ya no esté.

**Alternativas descartadas**:

- *Mostrar a todos y que la interfaz los distinga visualmente*: contradice el principio y ensucia el
  listado a medida que pasan los cuatrimestres.

---

## R7 — Alcance del frontend

**Decisión**: se tocan dos páginas y el cliente de API. En `Templates.jsx` se agregan editar y
retirar, con el aviso de alcance de FR-003. En `Usuarios.jsx` se ajusta el texto de la confirmación
de baja para que diga lo que ahora ocurre de verdad.

**Rationale**: el backend puede resolver todo, pero si la única forma de corregir una plantilla es
por API cruda, el defecto que motivó la feature sigue vivo para el administrador (SC-001 exige
"desde el portal"). La página `Templates.jsx` hoy solo tiene alta, así que el trabajo es agregar
acciones a una tabla que ya existe.

**No se toca** `Catedras.jsx`: la feature no cambia nada del ciclo de vida de las cátedras más allá
del mensaje que se muestra al desactivar a su titular, que vive en `Usuarios.jsx`.

---

## Resumen de decisiones

| Id | Decisión | Impacto |
|---|---|---|
| R1 | Retirar plantilla = `activo = False`, sin campos nuevos | Sin migración |
| R2 | El pedido aprobado se despliega con lo reservado, no con la plantilla editada | **El despliegue hoy lee la plantilla: hay que cambiarlo.** Prueba de capacidad obligatoria |
| R3 | `DELETE /usuarios` pasa a baja lógica; borrado real solo sin historial | Cambia el código de respuesta |
| R4 | Tres guards en el retiro, incluido el último administrador | Guard nuevo |
| R5 | Se corrige el mensaje, no el guard ni la consulta | Cambio de texto |
| R6 | Los listados ocultan retiradas por defecto | Cambia una consulta |
| R7 | Editar y retirar plantillas desde la interfaz | Dos páginas |

**Ningún `NEEDS CLARIFICATION` queda abierto.**
