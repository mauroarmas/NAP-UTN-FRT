# Quickstart de validación: 006-ciclo-vida-entidades

**Feature**: 006-ciclo-vida-entidades | **Fecha**: 2026-08-30

Guía para validar la feature una vez implementada. Sigue el formato de la
[validación de la 004](../004-unificar-usuario-catedra/quickstart.md), cuya ejecución contra
infraestructura real es la que destapó los tres defectos que esta feature corrige.

---

## Prerrequisitos

- Stack levantado: `docker compose up -d` (API en `:8001`, frontend en `:5174`, PostgreSQL en `:5434`)
- Proxmox alcanzable y con el token configurado en `.env`
- Al menos una plantilla, una cátedra y un servicio desplegado

```bash
# Autenticación para los escenarios de API
ADMIN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -d "username=admin&password=admin" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
```

---

## 1. Pruebas automatizadas

```bash
cd backend && ./venv/bin/python -m pytest -q
```

Deben pasar las existentes (201 al cierre de la feature 004) más las nuevas:

| Archivo | Cubre |
|---|---|
| `test_templates_edicion.py` | FR-001 a FR-008, reglas T1–T6 |
| `test_despliegue_usa_reserva.py` | **R2 / FR-002 — compuerta de capacidad** |
| `test_usuarios_retiro.py` | FR-009 a FR-015, reglas U1–U8 |
| `test_mensajes_bloqueo.py` | FR-016, FR-017 |

```bash
cd frontend && npm run build   # sin errores
```

---

## 2. Escenarios de validación manual

### E1 — Corregir una plantilla rota (US1) — **el escenario que motivó la feature**

Reproduce exactamente lo que ocurrió el 2026-08-29, cuando no hubo forma de arreglarlo desde el
portal.

1. Crear una plantilla con `os_template` apuntando a una imagen que **no existe** en el nodo.
2. Pedirla desde una cátedra, aprobarla y desplegarla → **falla**, como se espera.
3. **Corregir** la plantilla desde la interfaz, apuntándola a una imagen real.
4. Crear un pedido nuevo con ella, aprobarlo y desplegarlo → **funciona**.
5. Verificar que no hizo falta tocar la base de datos en ningún momento (SC-001).

### E2 — Editar no toca lo ya entregado (US1, FR-002) — **bloqueante**

1. Con un servicio desplegado de 1 vCPU / 256 MB, anotar sus valores.
2. Editar su plantilla y dejarla en 4 vCPU / 2048 MB.
3. Verificar en el portal **y en Proxmox** que el contenedor sigue con 1 vCPU / 256 MB.
4. Verificar que el servicio no se reinició ni se recreó (mismo VMID, mismo `deployed_at`).

### E3 — La plantilla cambia entre aprobar y desplegar (R2) — **el bloqueante crítico**

Es el escenario que esta feature vuelve alcanzable y que, sin la corrección de R2, produciría una
fuga de capacidad silenciosa.

1. Anotar `libre` de `GET /capacidad`.
2. Pedir un servicio con una plantilla de **1 vCPU**. Aprobarlo. Anotar `reserva_vcpus` del pedido y
   el nuevo `libre`.
3. **Sin desplegar**, editar la plantilla y dejarla en **4 vCPU**.
4. Desplegar el pedido.
5. **Verificar que el contenedor se creó con 1 vCPU**, no con 4. Si tiene 4, la reserva y lo
   desplegado quedaron desacoplados y el clúster está sobrecomprometido sin que nadie lo aprobara.
6. Verificar que `desplegado` en `GET /capacidad` coincide con lo que estaba reservado.

### E4 — Retirar una plantilla del catálogo (US1)

1. Retirar una plantilla que tenga servicios desplegados.
2. Verificar que **no** aparece al crear un pedido nuevo.
3. Intentar crear un pedido con su id de todos modos → rechazado con explicación (FR-005).
4. Abrir un pedido histórico que la usaba → **sigue mostrando la plantilla** correctamente (FR-006).
5. Verificar que los servicios desplegados con ella siguen corriendo.

### E5 — Retirar a un docente con historial (US2) — **bloqueante**

Es el caso que hoy termina en 500.

1. Con una persona que creó pedidos, retirarla desde la interfaz.
2. **Verificar que la operación se completa sin error técnico** y que el portal dice qué pasó.
3. Verificar que no puede iniciar sesión.
4. Abrir los pedidos que había creado → **siguen mostrando quién los pidió** (FR-010).
5. Verificar que no aparece en el listado de personas, pero sí al pedir `?incluir_bajas=true`.

### E6 — Retirar a alguien sin historial (US2)

1. Crear una cuenta y no hacer nada con ella.
2. Retirarla.
3. Verificar que la fila **se eliminó** de verdad, y que quien la retiró no tuvo que saber de antemano
   en cuál de los dos casos estaba.

### E7 — Los guards del retiro (US2, FR-013)

1. Con un solo administrador activo, intentar retirarlo → **409 `ultimo_administrador`**.
2. Crear un segundo administrador, reintentar → ahora sí se puede.
3. Verificar que retirarse a uno mismo sigue bloqueado.

### E8 — Un mensaje que dice cómo salir (US3, FR-016) — **bloqueante**

Es la prueba de que el defecto quedó realmente cerrado.

1. Intentar dar de baja a una persona titular de una cátedra → bloqueado, con las cátedras nombradas.
2. **Hacer literalmente lo que el mensaje dice** (reasignar el titular).
3. Reintentar → **se completa**.
4. Verificar que el mensaje **ya no sugiere dar la cátedra de baja**, porque eso no destraba nada.

### E9 — El bloqueo sigue aplicando con la cátedra dada de baja (FR-017)

Impide que alguien "optimice" el guard más adelante.

1. Dar de baja una cátedra que tiene servicios vigentes (confirmando).
2. Intentar dar de baja a su titular.
3. **Verificar que sigue bloqueado**: la cátedra inactiva conserva servicios corriendo y necesita
   responsable.

### E10 — Nada devuelve un error técnico (FR-015)

Recorrer todos los intentos fallidos de E4 a E9 y verificar que **ninguno** expone un error crudo:
todos traen código, mensaje entendible y, cuando corresponde, la salida concreta.

---

## 3. Verificación contra Proxmox

Para E2 y E3, contrastar contra la fuente de verdad:

```bash
source .env
AUTH="PVEAPIToken=root@pam!ps-dev=${PROXMOX_TOKEN_VALUE}"
curl -sk -H "Authorization: $AUTH" \
  "https://${PROXMOX_HOST}:8006/api2/json/nodes/proxmox/lxc/<VMID>/config" \
  | python3 -m json.tool | grep -E "cores|memory|rootfs"
```

Los valores deben coincidir con lo que el pedido tenía **reservado**, no con los de la plantilla
vigente.

---

## Criterios de aceptación de la validación

| Escenario | Requisitos | Bloqueante |
|---|---|---|
| Suite de pruebas en verde | Compuerta constitucional | ✅ |
| E3 (la plantilla cambia entre aprobar y desplegar) | R2, FR-002 | ✅ |
| E5 (retirar con historial, sin 500) | FR-009, FR-010, FR-015 | ✅ |
| E8 (el mensaje indica una salida real) | FR-016 | ✅ |
| E2 (editar no toca lo entregado) | FR-002 | ✅ |
| E1, E4, E6, E7, E9, E10 | US1–US3 | ⚠ |

**E3 es el más importante**: es el único que puede producir una fuga de capacidad silenciosa, y es un
riesgo que esta misma feature introduce si se implementa a medias.


---

## Estado de la validación (2026-08-30)

Ejecutada contra **Proxmox VE 9.2.2** (nodo `proxmox`) y **PostgreSQL 16** en
Docker Compose. `pytest`: **246 pruebas en verde** (201 antes de la feature,
+45 nuevas). `npm run build`: sin errores.

| Escenario | Resultado | Cómo se verificó |
|---|---|---|
| **E1** — corregir una plantilla rota | ✅ PASA | `os_template` corregido vía API, sin tocar la base — el defecto que motivó la feature |
| **E2** — editar no toca lo entregado | ✅ PASA | Plantilla llevada a 4 vCPU/4096 MB; el servicio (VMID 101) siguió en 1 vCPU/256 MB, confirmado en la config real de Proxmox |
| **E3** — la plantilla cambia entre aprobar y desplegar | ✅ PASA | Aprobado por 1 vCPU, plantilla agrandada a 4, desplegado: **Proxmox reporta `cores: 1`**. La fuga queda cerrada |
| **E4** — retirar del catálogo | ✅ PASA | Deja de ofrecerse; pedirla da 404; el admin la ve con `?incluir_retiradas=true`; el historial la resuelve |
| **E5** — retirar a un docente con historial | ✅ PASA | HTTP **200** (antes 500), `resultado: desactivado`, el pedido conserva `solicitante_id` |
| **E6** — retirar a alguien sin historial | ✅ PASA | `resultado: eliminado`, la fila desaparece |
| **E7** — guards | ✅ PASA | Retirarse a uno mismo → 400 |
| **E8** — el mensaje indica una salida real | ✅ PASA | Aconseja reasignar; hacerlo destrabó la operación; ya no sugiere dar la cátedra de baja |
| **E9** — el bloqueo sigue con la cátedra inactiva | ✅ PASA | 409 con la cátedra en `activa=false` (FR-017) |
| **E10** — ningún error sin traducir | ✅ PASA | Seis caminos de error barridos: 404/400/409 con mensaje legible, **cero 500** |

### Ampliaciones detectadas durante la implementación

- **`GET /templates/?incluir_retiradas=true`** no estaba en el contrato. Sin él,
  retirar una plantilla era un camino de ida desde la interfaz: el catálogo solo
  devuelve las activas, así que el administrador no tenía forma de encontrarla
  para volver a habilitarla. Se agregó, restringido al rol administrador.

- **El guard del último administrador (FR-013) es inalcanzable por la API.** Para
  llamar al endpoint hay que ser administrador activo, y el chequeo de "no podés
  eliminarte a vos mismo" corre antes: quien llama es siempre otro administrador
  activo, así que la condición nunca se cumple. Se conserva como defensa en
  profundidad para caminos futuros y se prueba sobre el helper
  (`es_ultimo_admin_activo`) en lugar de sobre el endpoint. Queda documentado en
  el código para que nadie lo lea como cobertura que no es.
