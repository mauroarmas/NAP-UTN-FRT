# Data Model: Retirar y corregir usuarios, cátedras y plantillas

**Feature**: 006-ciclo-vida-entidades | **Fecha**: 2026-08-30

> **Esta feature no requiere migración de esquema.** Todos los campos que necesita ya existen. Lo que
> cambia es la **semántica** de operaciones que hoy los ignoran o los usan mal. Este documento
> describe esas reglas, no columnas nuevas.

---

## Glosario

Cuatro verbos vecinos que conviene no mezclar:

| Término | Significa |
|---|---|
| **Retirar** | El paraguas: sacar de circulación una persona o una plantilla. No dice **cómo**. |
| **Desactivar** | Uno de los dos desenlaces del retiro: `activo = false`, la fila permanece. |
| **Borrar** | El otro desenlace: la fila se elimina. Solo para cuentas sin historial (U2). |
| **Dar de baja** | Sinónimo de desactivar, heredado del vocabulario de pedidos y servicios (feature 001). |

Cuando el texto dice "retirar", el sistema elige entre desactivar y borrar según haya historial;
quien ejecuta la acción no necesita saber de antemano cuál de las dos ocurrirá.

---

## Entidades afectadas

### RecursoTemplate

Sin cambios estructurales. La feature habilita la escritura de campos que hoy solo se pueden fijar en
el alta.

| Campo | Tipo | Rol en esta feature |
|---|---|---|
| `nombre` | `varchar(100)`, único | Editable. Debe seguir siendo único. |
| `descripcion` | `text?` | Editable |
| `tipo` | enum `lxc` / `qemu` | **No editable** — ver regla T4 |
| `default_vcpus` | `int` | Editable |
| `default_ram_mb` | `int` | Editable |
| `default_disk_gb` | `int` | Editable, sujeto al tope de disco |
| `justificacion_disco` | `text?` | Editable; obligatoria si el disco supera el tope |
| `os_template` | `varchar(200)?` | Editable — **es el campo que motivó la feature** |
| `config_extra` | `json?` | Editable |
| `activo` | `bool` | Pasa a ser accionable: retirar = `false` |

**Reglas**:

- **T1** — Editar una plantilla no modifica ningún servicio ya desplegado. Los servicios guardan sus
  propios `vcpus_asignados`, `ram_asignada_mb` y `disk_asignado_gb`, fijados al desplegar.
- **T2** — Editar no modifica los pedidos aprobados pendientes: se despliegan con `reserva_vcpus`,
  `reserva_ram_mb` y `reserva_disk_gb` del propio pedido (R2).
- **T3** — El tope de disco y su exigencia de justificación rigen igual en la edición que en el alta
  (`limites_service.validar_disco`).
- **T4** — El `tipo` no es editable. Cambiar un `lxc` por un `qemu` altera la naturaleza de lo que se
  entrega y de lo que ya se aprobó sobre esa plantilla; para eso corresponde una plantilla nueva.
- **T5** — Retirar una plantilla (`activo = false`) no la borra: los pedidos y servicios que la
  referencian la siguen resolviendo por id.
- **T6** — El nombre debe seguir siendo único al editar, excluyendo la propia plantilla de la
  comprobación.

**Ciclo de vida**:

```text
              crear                editar (n veces)
                │                        ↕
                ▼                        │
         ┌─────────────┐  retirar  ┌─────────────┐
         │   activa    │──────────▶│  retirada   │
         │ (en catálogo)│◀──────────│(fuera de él)│
         └─────────────┘ reactivar └─────────────┘
                │                        │
                └────────┬───────────────┘
                         ▼
        legible siempre desde pedidos y servicios históricos
```

Reactivar es simplemente `activo = true`; no requiere tratamiento especial.

---

### Usuario

Sin cambios estructurales. La feature cambia qué significa "eliminar".

| Campo | Tipo | Rol en esta feature |
|---|---|---|
| `activo` | `bool` | Pasa a ser el mecanismo de retiro |
| `rol` | enum `admin` / `catedra_admin` | Determina si aplica el guard del último administrador |

**Reglas**:

- **U1** — Retirar a una persona **con historial** (algún pedido creado, o alguna cátedra a cargo)
  es una baja lógica: `activo = false`, la fila permanece.
- **U2** — Retirar a una persona **sin historial** puede borrar la fila: no hay nada que preservar.
- **U3** — La autoría de un pedido (`pedidos.solicitante_id`) **nunca** se anula ni se reasigna.
- **U4** — Una persona inactiva no puede iniciar sesión. *(Ya se cumple hoy:
  `routers/auth.py:48` y `:81`.)*
- **U5** — Los listados operativos excluyen a las personas retiradas por defecto; el detalle por id
  las sigue resolviendo.
- **U6** — No se puede retirar al último administrador **activo**.
- **U7** — No se puede retirar a uno mismo. *(Ya se cumple hoy.)*
- **U8** — No se puede retirar a quien tiene cátedras a cargo, esté la cátedra activa o no.

**Orden de verificación** (importa: determina qué mensaje recibe la persona):

```text
  retirar(usuario)
      │
      ├─ ¿soy yo?                          → 400 "No podés eliminarte a vos mismo"
      ├─ ¿es el último admin activo?        → 409 último_administrador
      ├─ ¿tiene cátedras a cargo?           → 409 catedras_sin_responsable
      │
      ├─ ¿tiene pedidos?  ── sí ──▶ baja lógica (activo = false)
      │                    └─ no ──▶ borrado real
      ▼
   200 con el resultado ("desactivado" | "eliminado")
```

---

### Catedra

**No se modifica.** Participa solo como condición de bloqueo (U8). Se documenta explícitamente que su
campo `activa` **no** interviene en esa verificación: una cátedra dada de baja puede conservar
servicios corriendo, así que sigue necesitando responsable (R5, FR-017).

---

### Pedido y Servicio

**No se modifican estructuralmente.** Cambia de dónde salen los valores al desplegar:

- **P1** — El despliegue arma el contenedor con `pedido.reserva_vcpus`, `pedido.reserva_ram_mb` y
  `pedido.reserva_disk_gb`, no con los `default_*` de la plantilla (R2).
- **P2** — El servicio se registra con esos mismos valores, para que lo reservado, lo desplegado y lo
  registrado coincidan siempre.

> Los campos `reserva_*` ya existen desde la feature 004 y ya se llenan al aprobar; hoy simplemente no
> se leen al desplegar.

---

## Invariantes que la feature debe preservar

| # | Invariante | Por qué |
|---|---|---|
| I1 | Ningún pedido queda sin solicitante | Principio V; es lo que hoy produce el 500 |
| I2 | Lo reservado, lo desplegado y lo registrado coinciden | Principio IV; R2 |
| I3 | El sistema siempre tiene al menos un administrador activo | Recuperabilidad operativa |
| I4 | Toda cátedra con servicios vigentes tiene titular activo | Principio IV; ya lo sostiene el guard |
| I5 | Una plantilla referenciada por historial siempre se resuelve | Principio V |

---

## Qué NO cambia

Para acotar el alcance y facilitar la revisión:

- No hay migraciones de Alembic.
- No se agregan tablas, columnas ni enums.
- No se toca la máquina de estados de pedidos ni de servicios.
- No se toca el cálculo de capacidad (`capacidad_service`), solo **de dónde lee** el despliegue.
- No cambian los permisos: todo lo mutante sigue siendo exclusivo del administrador.
