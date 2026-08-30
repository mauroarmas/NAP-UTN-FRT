# Quickstart: validación de 004-unificar-usuario-catedra

**Fecha**: 2026-08-16

Guía para verificar que la feature funciona de punta a punta. No contiene código de implementación:
para el detalle de esquema ver [data-model.md](./data-model.md), para el de endpoints
[contracts/api.md](./contracts/api.md).

---

## Prerrequisitos

- PostgreSQL corriendo y `DATABASE_URL` configurada.
- Acceso al clúster Proxmox para los escenarios manuales (los automatizados usan el doble de
  prueba).
- Copia de seguridad de la base **antes** de migrar: la secuencia elimina columnas (cuotas) y
  reasigna titularidades.

```bash
cd backend
pip install -r requirements.txt      # incluye APScheduler (nuevo)
```

---

## 1. Pruebas automatizadas

Es la primera compuerta: la constitución (v2.0.0) exige pruebas para todo lo que toque orquestación,
máquina de estados o control de capacidad, **más** un escenario de concurrencia.

```bash
cd backend
pytest                                   # suite completa
pytest tests/test_capacidad_reserva.py   # reserva y atomicidad
pytest tests/test_aislamiento_multicatedra.py -v
```

**Qué tiene que pasar**:

- Toda la suite en verde, sin Proxmox real (doble de prueba en `tests/fakes.py`).
- `test_soft_delete_cuota.py` queda **reescrito**, no borrado: la regla de fondo que verificaba
  —lo dado de baja no ocupa capacidad— sobrevive en el modelo nuevo; lo que cambia es contra qué se
  mide.
- La prueba de aislamiento recorre **todos** los endpoints de listado con un usuario de dos
  cátedras y una tercera ajena poblada. Es la red que atrapa el punto de filtrado que se haya
  omitido (riesgo 10 de la spec).

---

## 2. Migración

```bash
cd backend
alembic upgrade head
```

**Verificaciones posteriores**, en este orden:

1. **Nadie perdió acceso en silencio** (FR-034):
   ```
   GET /api/v1/admin/migracion/accesos-perdidos
   ```
   Si devuelve filas, cada persona listada necesita que el administrador le cree o reasigne una
   cátedra. La migración es correcta aunque la lista no esté vacía — lo incorrecto sería que la
   lista no existiera.

2. **Toda cátedra activa tiene titular**: ninguna fila con `titular_id IS NULL` y `activa = true`.

3. **Ningún servicio quedó sin dueño**: el conteo de servicios por cátedra es idéntico antes y
   después (FR-032, Principio V).

4. **Los servicios preexistentes tienen `vence_at` nulo** y por lo tanto no se apagan solos. El
   administrador les asigna fecha desde el panel.

---

## 3. Escenarios de validación manual

### E1 — Una sola cuenta, varias cátedras (US1)

1. Crear un usuario con **tres** cátedras desde el alta (`POST /usuarios/`).
2. Iniciar sesión con esa cuenta **una sola vez**.
3. Verificar: se ven los servicios y pedidos de las tres, cada uno rotulado con su cátedra, y nada
   de una cuarta cátedra ajena.
4. Crear un segundo usuario con **una** cátedra: no debe aparecerle ningún selector (FR-005).

### E2 — El buscador de cátedras no se ensucia (US1, FR-035b/c)

1. Abrir el alta de usuario con al menos 20 cátedras cargadas, varias ya con titular.
2. Escribir "prog": la lista filtra en el momento.
3. Las cátedras ya tomadas se ven **deshabilitadas con su titular al lado**, no ocultas.
4. Marcar tres: aparecen como fichas removibles arriba, sin que haya que scrollear para saber qué
   se eligió.
5. Confirmar sin marcar ninguna → error claro (FR-036b).

### E3 — Pedir sin toparse con una cuota (US2)

1. Con una cátedra que bajo el modelo viejo habría excedido cualquier cuota, crear un pedido.
2. Verificar: queda en `solicitado` y aparece en la bandeja del administrador. **No** hay 409.
3. Intentar crear un pedido a nombre de una cátedra ajena → 403.

### E4 — Aprobar reserva capacidad (US3) — **el escenario crítico**

Es el que valida la corrección que motivó el rediseño. Requiere dos pedidos.

1. Anotar `libre` de `GET /capacidad`.
2. Abrir `GET /pedidos/{A}/evaluacion` y anotar `libre_si_aprueba`.
3. Aprobar A.
4. Abrir `GET /pedidos/{B}/evaluacion` **sin desplegar A todavía**.
5. **Verificar que `libre` ya descuenta A.** Si sigue mostrando el saldo original, la reserva no
   está funcionando y el modelo entero queda comprometido.
6. Aprobar B con un `capacidad_token` viejo (el del paso 2) → **409 `token_desactualizado`** con
   los números nuevos.

### E5 — Sobrecompromiso deliberado (FR-015, FR-015b)

1. Aprobar pedidos hasta que `excede_capacidad` sea `true`.
2. Aprobar sin justificación → 400.
3. Aprobar con justificación → 200, y la justificación queda registrada y consultable.

El sistema **no** debe impedir la aprobación: la decisión es del administrador.

### E6 — La reserva vence sola (FR-018d)

1. Aprobar un pedido y **no** desplegarlo.
2. Adelantar `reserva_expira_at` en la base, o ejecutar
   `POST /admin/jobs/expirar_reservas`.
3. Verificar: la capacidad vuelve a estar libre, el pedido quedó en un estado explícito, y el
   historial registra la acción con autor **sistema** (no una persona).

### E7 — Pausado por inactividad (US4)

1. Con un servicio en ejecución y métricas cargadas por debajo del umbral durante la ventana,
   ejecutar `POST /admin/jobs/evaluar_inactividad`.
2. Verificar que queda **avisado y programado**, no pausado todavía (FR-020).
3. Generar actividad y volver a ejecutar → el aviso se cancela (FR-021).
4. Sin actividad, vencida la gracia → queda `paused`, y en Proxmox el contenedor está **detenido**
   (es lo que libera CPU y RAM de verdad — R7).
5. Reactivar desde la cátedra: vuelve a `running` con sus datos (FR-023). Advertir que los procesos
   levantados a mano no vuelven solos (FR-023b).
6. Marcar otro servicio como `exento_pausado` y comprobar que no se pausa, pero **sí** aparece en
   `GET /servicios/exentos-inactivos`.

### E8 — El silencio no es inactividad (FR-028) — **la prueba que más importa**

1. Detener la recolección de métricas durante una ventana completa.
2. Ejecutar `POST /admin/jobs/evaluar_inactividad`.
3. **Verificar que no se pausó ningún servicio.** Un falso positivo acá apaga trabajo en uso y es
   más caro que no pausar nada nunca.

### E9 — Vencimiento y renovación (US6)

1. Aprobar un pedido y verificar que el servicio nace con `vence_at` **visible para la cátedra**
   (FR-018g).
2. Adelantar la fecha hasta la ventana de aviso → la cátedra ve el aviso.
3. Solicitar renovación: llega a la bandeja del administrador con la misma información de capacidad
   que un pedido nuevo, y **sin reservar capacidad nueva** (R11).
4. Aprobar: el servicio **conserva su id y sus datos**; solo corre `vence_at` (FR-018j). Verificar
   que no se recreó el contenedor.
5. Con una renovación **pendiente**, dejar pasar el vencimiento → el servicio **no** se apaga
   (FR-018m).
6. Sin renovación, vencido → se libera cómputo y memoria, los datos siguen (FR-018k).

### E10 — El aislamiento no se filtró (FR-003) — regresión

Con un usuario de dos cátedras y una tercera ajena con pedidos, servicios y métricas: recorrer cada
pantalla y cada listado. **Ningún** recurso de la tercera debe aparecer en ninguna parte.

Cubierto también por `test_aislamiento_multicatedra.py`; el paso manual existe porque el riesgo es
de omisión, y una pantalla que nadie miró es tan probable como un endpoint que nadie filtró.

---

## 4. Verificación del planificador

```bash
cd backend && uvicorn app.main:app --reload
```

Al arrancar deben quedar registrados los cuatro trabajos (métricas, inactividad, vencimientos,
reservas). Con más de un worker, verificar que **no** se ejecutan por duplicado: el lock de
`job_locks` debe impedirlo (R1).

---

## Criterios de aceptación de la validación

| Escenario | Requisitos | Bloqueante |
|---|---|---|
| Suite de pruebas en verde | Compuerta constitucional | ✅ |
| E4 (la reserva descuenta) | FR-018b/c | ✅ |
| E8 (silencio ≠ inactividad) | FR-028 | ✅ |
| E10 (sin fugas entre cátedras) | FR-003 | ✅ |
| E6, E9 | FR-018d, FR-018j/m | ✅ |
| E1, E2, E3, E5, E7 | US1–US4 | ⚠ |

---

## Estado de la validación

### Ejecutada contra entorno real (2026-08-29)

Validación completa de T091 contra **Proxmox VE 9.2.2** (nodo `proxmox`, 4 vCPU,
7892 MB RAM, 72 GB) y **PostgreSQL 16** en Docker Compose.

`pytest`: **201 pruebas en verde**. Frontend sirviendo en :5174.

| Escenario | Resultado | Cómo se verificó |
|---|---|---|
| **E1** — una cuenta, varias cátedras | ✅ PASA | Titular de 2 cátedras en una sesión; pedidos rotulados por cátedra |
| **E2** — el buscador no se ensucia | ✅ PASA (navegador) | Recorrido con Playwright sobre 24 cátedras: "prog" filtra 24→4; las tomadas quedan **deshabilitadas en gris con su titular al costado**, no ocultas; 3 elegidas aparecen como fichas removibles; sin cátedra el alta se bloquea con "Asigná al menos una cátedra" |
| **E3** — pedir sin toparse con cuota | ✅ PASA | Pedido queda `solicitado`, sin 409; cátedra ajena → 403 |
| **E4** — aprobar reserva capacidad | ✅ PASA | Con `desplegado`=0, `reservado`=1/256/8 y `libre` ya descontado; token viejo → 409 `token_desactualizado` |
| **E5** — sobrecompromiso deliberado | ✅ PASA | Sin justificación → 400; con justificación → 200 y queda registrada |
| **E6** — la reserva vence sola | ✅ PASA | `expirar_reservas` liberó la capacidad; historial con autor **sistema** (`usuario_id=None`) |
| **E7** — pausado por inactividad | ✅ PASA | Avisa con 48 h de gracia; la actividad cancela el aviso; al vencer pausa y **el contenedor queda `stopped` en Proxmox** (R7, mem 0/cpu 0); reactivar conserva disco e id; `exento_pausado` omite pero sigue listado |
| **E8** — el silencio no es inactividad | ✅ PASA | Con 0 métricas, el job omitió con motivo explícito `sin_cobertura` |
| **E9** — vencimiento y renovación | ✅ PASA | Renovación no reserva capacidad nueva (0/0/0); al ejecutarla el servicio conserva id, VMID y `deployed_at`, solo corre `vence_at`; un solo contenedor en Proxmox |
| **E10** — el aislamiento no se filtró | ✅ PASA | 403 en ambas direcciones, lectura y escritura, incluido `console-ticket` |
| **Sección 4** — planificador multi-worker | ✅ PASA | Dos procesos contra la misma base: uno ejecuta, el otro recibe "ya está en ejecución" (R1) |

### Migraciones contra PostgreSQL real

Ejecutadas las 7 revisiones desde `base` sobre PostgreSQL, y además la ruta
realista **con datos preexistentes**: se montó el esquema pre-004, se cargaron
tres cátedras (una con 3 docentes insertados fuera de orden, una con 1, una
huérfana) y se corrió `alembic upgrade head`.

- Titular elegido = `MIN(id)`, **no** el orden de inserción. Verificado.
- Cátedra sin docentes → `titular_id` NULL, sin romper.
- `migracion_004_accesos_perdidos` registró exactamente a los dos que perdieron acceso.
- `usuarios.catedra_id` y las columnas de cuota, eliminadas.
- `downgrade` hasta pre-004 corre limpio (reversibilidad).

### Defecto encontrado y corregido

`e2f3a4b5c6d7` creaba el enum `tipopedido` con etiquetas en **minúscula**
(`"alta"`, `"renovacion"`), mientras SQLAlchemy persiste el **nombre** del
miembro (`ALTA`). Toda consulta que filtrara por `pedidos.tipo` fallaba contra
PostgreSQL con `InvalidTextRepresentationError`, dejando `GET /capacidad` en 502
— es decir, el núcleo de esta feature caído. Los otros cuatro enums del esquema
ya usaban mayúscula; este era el único fuera de convención.

**Por qué las pruebas no lo detectaban**: SQLite no tiene enums nativos, así que
`create_all` genera un VARCHAR coherente con el modelo y el desajuste es
invisible. Es exactamente la clase de defecto que esta validación existe para
encontrar.

### Recorrido visual de E2 (2026-08-29)

Ejecutado con Playwright/Chromium sobre el frontend real, con 24 cátedras
cargadas (4 con titular, 20 libres). Capturas en el scratchpad de la sesión.

| Paso | Resultado |
|---|---|
| 1. Selector con 20+ cátedras | ✅ aparece poblado |
| 2. Escribir "prog" filtra en el momento | ✅ 24 → 4 (Paradigmas, Concurrente, I, II) |
| 3. Tomadas deshabilitadas **con su titular al lado**, no ocultas | ✅ "Catedra Ajena T091" en gris con "Docente Ajeno" al costado; `title="Ya es responsabilidad de Docente Ajeno"` |
| 4. Marcar tres → fichas removibles arriba | ✅ 3 fichas; quitar una deja 2 |
| 5. Confirmar sin ninguna → error claro (FR-036b) | ✅ banner rojo "Asigná al menos una cátedra"; el usuario **no** se crea |

Verificado además que el rol Administrador, cuyo label declara la cátedra
"(opcional para un administrador)", efectivamente permite crear la cuenta sin
ninguna asignada: la obligatoriedad aplica solo al rol cátedra.

> [!NOTE]
> En una primera pasada este paso 5 dio un falso positivo: el script no llegaba a
> completar los campos requeridos, así que el alta se bloqueaba por eso y no por
> la cátedra faltante. La verificación de arriba es la buena — campos completos,
> rol `catedra_admin` explícito y solo la cátedra ausente.

### Pendiente

Nada. La validación de T091 está completa.

### Defectos que esta validación dejó abiertos (resueltos el 2026-08-30)

Los tres hallazgos que T091 no podía corregir por estar fuera de su alcance
quedaron cubiertos por la [feature 006](../006-ciclo-vida-entidades/spec.md):

| Hallazgo | Dónde se resolvió |
|---|---|
| Las plantillas no se podían corregir ni retirar (hubo que hacer UPDATE por SQL) | 006 US1 |
| `DELETE /usuarios` devolvía 500 con una persona que tenía pedidos | 006 US2 |
| El mensaje de bloqueo aconsejaba dar la cátedra de baja, que no destraba nada | 006 US3 |

Un cuarto defecto —el arranque del backend abortaba con más de un administrador,
porque `seed_admin.py` usaba `scalar_one_or_none()` para preguntar "¿hay
alguno?"— se corrigió en el momento, durante la propia limpieza.

Al implementar la 006 apareció además un defecto latente que esta validación no
podía ver: el despliegue armaba el contenedor con los valores de la plantilla y
no con los que el pedido había reservado. Era inofensivo mientras las plantillas
fueran inmutables; habilitarlas para edición lo volvía una fuga de capacidad.
Corregido en la 006 (FR-018).
