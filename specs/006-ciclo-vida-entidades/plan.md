# Implementation Plan: Retirar y corregir usuarios, cátedras y plantillas

**Branch**: `006-ciclo-vida-entidades` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-ciclo-vida-entidades/spec.md`

## Summary

La feature cierra el ciclo de vida de las tres entidades administrativas del portal: permite
**corregir y retirar plantillas**, convierte el retiro de personas en una **baja lógica** que
preserva la autoría de sus pedidos, y arregla un mensaje de bloqueo que aconseja una salida que no
funciona.

El hallazgo que define el enfoque: **casi toda la maquinaria ya existe**. La inspección del código
muestra que `RecursoTemplate` ya tiene el campo `activo`, que el catálogo ya lo filtra, que
`crear_pedido` ya rechaza plantillas inactivas, y que el login ya rechaza usuarios inactivos. Lo que
falta no es un mecanismo nuevo sino **las puertas para accionarlo**: no hay endpoint para editar o
retirar una plantilla, y el borrado de usuarios es físico en vez de lógico.

En consecuencia el plan es deliberadamente conservador: agrega dos endpoints, cambia la semántica de
uno, corrige un filtro de listado y reescribe un mensaje. No introduce entidades, no migra datos y no
toca la máquina de estados ni la contabilidad de capacidad.

## Technical Context

**Language/Version**: Python 3.12 (backend), JavaScript ES2022 + React 18 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, proxmoxer;
React + Vite en el frontend

**Storage**: PostgreSQL 16 vía SQLAlchemy async. **Esta feature no requiere migración de esquema**:
todos los campos que necesita (`usuarios.activo`, `recurso_templates.activo`) ya existen.

**Testing**: pytest con doble de prueba del cliente Proxmox (`backend/tests/fakes.py`); las pruebas
corren sobre SQLite con `create_all`

**Target Platform**: Linux server en Docker Compose; el portal se despliega como servicio dentro del
propio clúster

**Project Type**: Aplicación web (backend FastAPI + SPA React)

**Performance Goals**: No aplica. El volumen es de decenas de plantillas y personas, y las
operaciones son administrativas y esporádicas.

**Constraints**: Ningún error técnico sin traducir puede llegar a la persona usuaria (FR-015). La
corrección de plantillas MUST NOT alterar servicios ya desplegados (FR-002).

**Scale/Scope**: ~20 cátedras, decenas de personas, unas pocas plantillas. 3 archivos de router,
2 de schema, 1 de servicio y 2 páginas de frontend.

### Estado del código relevante (verificado el 2026-08-30)

Lo que **ya funciona** y esta feature reutiliza en vez de reconstruir:

| Pieza | Dónde | Estado |
|---|---|---|
| Campo `activo` en plantillas | `models/recurso_template.py` | Existe |
| El catálogo oculta plantillas inactivas | `routers/templates.py` (`listar_templates`) | Existe |
| Pedir una plantilla inactiva se rechaza | `services/pedido_service.py:100` | Existe |
| Consultar una plantilla por id ignora `activo` | `routers/templates.py` (`obtener_template`) | Existe — cumple FR-006 |
| Campo `activo` en personas | `models/usuario.py` | Existe |
| Login rechaza personas inactivas | `routers/auth.py:48` y `:81` | Existe — cumple FR-011 |
| Bloqueo por cátedras a cargo al desactivar | `routers/usuarios.py:152-165` | Existe, con el mensaje mal |
| Tope de disco con justificación | `services/limites_service.py` | Existe — se reutiliza en la edición |

Lo que **falta**:

| Hueco | Dónde | Requisito |
|---|---|---|
| No hay endpoint de edición ni retiro de plantillas | `routers/templates.py` | FR-001, FR-004 |
| `DELETE /usuarios/{id}` borra físicamente y revienta con 500 | `routers/usuarios.py:208` | FR-009, FR-010, FR-015 |
| `DELETE` no tiene el guard de cátedras que sí tiene `PATCH` | `routers/usuarios.py` | FR-016 |
| El listado de personas no filtra por `activo` | `routers/usuarios.py:22` | FR-012 |
| No hay protección del último administrador | `routers/usuarios.py` | FR-013 |
| El mensaje de bloqueo aconseja algo que no destraba | `routers/usuarios.py:159-162` | FR-016, FR-017 |
| El frontend no ofrece editar ni retirar plantillas | `pages/Templates.jsx` | FR-001, FR-004 |
| **El despliegue usa los valores de la plantilla, no los reservados por el pedido** | `services/orquestacion_service.py:203-205` y `:362-364` | **FR-018** — ver R2 |

## Constitution Check

*GATE: evaluado antes de Phase 0 y reevaluado tras Phase 1.*

Constitución vigente: **v2.0.0**.

| Principio | Evaluación | Veredicto |
|---|---|---|
| **I. Proxmox es el back-end, nunca la interfaz** | La feature no toca la frontera con Proxmox. Editar una plantilla cambia qué se pedirá en el futuro, no toca el clúster. | ✅ Sin impacto |
| **II. La máquina de estados es la única fuente de verdad** | No se agregan ni modifican transiciones de pedidos ni de servicios. El estado `activo` de personas y plantillas no forma parte de esa máquina. | ✅ Sin impacto |
| **III. Toda operación debe ser recuperable** | La feature **corrige** un incumplimiento: hoy `DELETE /usuarios` deja un 500 sin explicación. FR-015 lo alinea. | ✅ Mejora |
| **IV. Aislamiento por cátedra; la capacidad se controla al aprobar** | Zona sensible y **con trabajo obligatorio**: se verificó que el despliegue arma el contenedor con los valores de la plantilla y no con los que el pedido reservó (`orquestacion_service.py:203-205`). Habilitar la edición de plantillas sin corregir eso introduciría una fuga de capacidad silenciosa. Resuelto en research.md (R2). | ⚠️ Requiere corrección — planificada |
| **V. El historial académico no se destruye** | Es el principio que la feature viene a hacer cumplir: el borrado físico de personas destruye la autoría de pedidos. FR-010 lo corrige. Las plantillas retiradas siguen legibles desde su historial (FR-006). | ✅ Mejora |
| **VI. La cátedra pide y observa; el administrador gestiona** | Todo lo que agrega la feature es exclusivo del rol administrador (FR-008). La cátedra no gana ninguna capacidad nueva. | ✅ Sin impacto |
| **Seguridad: operaciones mutantes exigen rol administrador** | Editar y retirar plantillas, y retirar personas, quedan tras `require_admin`, como el resto. | ✅ Cumple |
| **Esquema versionado con Alembic; la base no se toca a mano** | La feature **elimina** la necesidad de violarlo: hoy corregir una plantilla obliga a hacer UPDATE por SQL, que fue exactamente lo que hubo que hacer el 2026-08-29. No introduce migraciones nuevas. | ✅ Mejora |

**Compuerta de pruebas**: la constitución exige pruebas automatizadas para todo código que toque
orquestación, máquina de estados o **control de capacidad**, con al menos un camino de fallo y un
escenario de concurrencia.

- La edición de plantillas **roza** el control de capacidad por el caso del pedido aprobado
  pendiente (R2, FR-018). Se declara **dentro** de la compuerta: lleva prueba dedicada, incluido el
  escenario de "la plantilla cambia entre la aprobación y el despliegue" y un camino de fallo de
  infraestructura simulado.
- El retiro de personas y el mensaje de bloqueo **no** tocan capacidad ni orquestación. Llevan
  pruebas igual —son código nuevo y modificado— pero no activan la exigencia de concurrencia.

**Sobre el escenario de concurrencia** (constitución: *"el código que decide sobre capacidad MUST
probarse además con al menos un escenario de concurrencia: dos decisiones simultáneas sobre la misma
capacidad disponible"*):

Esta feature **no agrega código que decida sobre capacidad**, y por eso no incorpora un escenario de
concurrencia nuevo. La distinción es deliberada y se registra acá para que no se lea como un olvido:

- **Quien decide** es la aprobación del pedido (`aprobar_pedido`), que verifica disponibilidad y crea
  la reserva dentro de un bloqueo. Eso es de la feature 004 y ya está cubierto por
  `backend/tests/test_capacidad_concurrencia.py`. Esta feature no lo modifica.
- **Lo que esta feature toca** es el despliegue, que **consume** una decisión ya tomada: pasa a leer
  los tres números que la aprobación dejó guardados en el pedido. No compara contra capacidad libre,
  no reserva y no puede perder una carrera contra otra decisión, porque no decide nada.

Más aún: la corrección de R2 **elimina** una carrera que hoy existe. Antes, editar una plantilla
mientras un despliegue está en vuelo puede alterar lo que ese despliegue crea; después, el despliegue
es inmune a lo que le pase a la plantilla. El escenario concurrente no queda sin probar: queda sin
poder ocurrir.

La prueba de T001 verifica exactamente esa inmunidad ejecutando la edición **entre** la aprobación y
el despliegue, que es la versión determinista y reproducible del mismo riesgo.

**Resultado de la compuerta (pre-Phase 0)**: ✅ **PASA**. Ninguna violación que justificar.

### Reevaluación post-diseño (tras Phase 1)

Revisada contra `research.md`, `data-model.md` y `contracts/api.md`:

| Punto | Resultado |
|---|---|
| ¿El diseño agregó transiciones de estado? | No. `activo` en personas y plantillas no forma parte de la máquina de estados de pedidos. **Principio II intacto.** |
| ¿El diseño introdujo migraciones o cambios de esquema? | No. Confirmado en `data-model.md`: todos los campos ya existen. **Restricción de Alembic intacta.** |
| ¿El diseño toca el cálculo de capacidad? | Solo **de dónde lee** el despliegue (R2/P1), no cómo se calcula. El cambio **corrige** una fuga en vez de abrir una. |
| ¿Quedó algún camino que destruya historial? | No. U3 lo prohíbe explícitamente y el borrado real se limita a cuentas sin nada que preservar (U2). |
| ¿Quedó algún error sin traducir? | No. El contrato enumera los códigos de `DELETE /usuarios` y declara que **ningún caso devuelve 500**. |
| ¿Alguna capacidad nueva para el rol cátedra? | No. Todo lo agregado exige administrador. |

**Cambio de alcance detectado en Phase 0**: la corrección del despliegue (R2) no estaba en la spec —
apareció al verificar el código. Entra en la feature porque **la US1 la vuelve necesaria**: habilitar
la edición de plantillas sin ella introduce una fuga de capacidad silenciosa. Es una ampliación
defendible del alcance, no un desvío: sin ella la feature deja el sistema peor que antes.

**Resultado post-diseño**: ✅ **PASA**. La sección Complexity Tracking queda vacía a propósito.

## Project Structure

### Documentation (this feature)

```text
specs/006-ciclo-vida-entidades/
├── plan.md              # Este archivo
├── research.md          # Phase 0 — decisiones de diseño
├── data-model.md        # Phase 1 — entidades y reglas
├── quickstart.md        # Phase 1 — guía de validación
├── contracts/
│   └── api.md           # Phase 1 — contrato de los endpoints
├── checklists/
│   └── requirements.md  # Checklist de calidad de la spec
└── tasks.md             # Phase 2 — lo genera /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   └── usuario.py                 # cascada de la relación pedidos (R3)
│   ├── routers/
│   │   ├── templates.py               # PATCH nuevo (editar y retirar)
│   │   └── usuarios.py                # DELETE pasa a baja lógica; guards; filtro; mensaje
│   ├── schemas/
│   │   └── template.py                # TemplateUpdate nuevo
│   └── services/
│       ├── limites_service.py         # se reutiliza sin cambios
│       ├── orquestacion_service.py    # desplegar con lo reservado, no con la plantilla (R2)
│       └── usuario_service.py         # helpers de retiro y del último admin
└── tests/
    ├── test_templates_edicion.py      # nuevo
    ├── test_templates_retiro.py       # nuevo
    ├── test_despliegue_usa_reserva.py # nuevo — compuerta de capacidad (R2/FR-018)
    ├── test_usuarios_retiro.py        # nuevo
    └── test_mensajes_bloqueo.py       # nuevo

frontend/
└── src/
    ├── pages/
    │   ├── Templates.jsx              # editar y retirar; aviso de alcance
    │   └── Usuarios.jsx               # retiro y su confirmación
    └── services/
        └── api.js                     # updateTemplate, retirarTemplate
```

**Structure Decision**: Se conserva la estructura de aplicación web ya establecida por las features
001–005 (backend FastAPI con routers/services/schemas separados, SPA React por páginas). La feature
no introduce carpetas ni capas nuevas: agrega un endpoint donde ya hay un router, un schema donde ya
hay schemas, y dos acciones en páginas que ya existen.

## Complexity Tracking

No hay violaciones a la constitución que justificar. La sección se deja vacía deliberadamente, según
lo previsto en Governance.
