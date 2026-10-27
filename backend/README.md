# Backend — Portal de Gestión (UTN FRT)

API del portal que media entre las cátedras y la infraestructura (Proxmox VE).
La gestión ocurre dentro del portal; la consola del contenedor propio es la
excepción acotada definida en la constitución y requiere aislamiento institucional.

Para continuar la spec 011 desde otra PC, seguir primero el
[traspaso](../docs/traspaso-011.md): entorno, datos privados y pendientes reales.

## Puesta en marcha

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install --require-hashes -r requirements.lock
./venv/bin/alembic upgrade head
./venv/bin/uvicorn app.main:app --reload
```

Documentación interactiva en `/api/docs`.

## Pruebas

Para SC-008 hay un laboratorio independiente con PostgreSQL dedicado, cien
servicios y12,96M muestras; no usa la configuración operativa. Seguir
[rendimiento-laboratorio.md](../docs/evidencia/009/rendimiento-laboratorio.md).
El p95 de navegador se mide por separado del diagnóstico HTTP/DB.

Python 3.12. El lock incluye dependencias transitivas con hashes. Para actualizarlo
deliberadamente desde la raíz: `uv pip compile backend/requirements.txt --python-version 3.12 --generate-hashes --no-strip-extras -o backend/requirements.lock`.

```bash
./venv/bin/python -m pytest
```

La suite ordinaria usa SQLite en memoria y dobles de PVE/SMTP/runner. Sin
TEST_DATABASE_URL omite explícitamente las pruebas marcadas postgres; el job
PostgreSQL de CI es obligatorio y no las omite. Hay un bloqueo de DNS/conexiones
reales por defecto, con excepción exclusiva del PostgreSQL aislado configurado.

Desde la raíz, iniciar el servicio temporal (no usa volúmenes persistentes):

```bash
docker compose -f docker-compose.test.yml up -d --wait
```

Después, desde backend:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://nap_test:nap_test_local_only@127.0.0.1:55432/nap_test_009
./venv/bin/python -m pytest --require-postgres -q tests/postgres
```

Las credenciales anteriores son solo del contenedor local de pruebas. Cada test
crea un esquema aleatorio propio y al terminar elimina únicamente ese esquema;
las conexiones son independientes. Antes de conectar, el helper rechaza hosts
externos, otra cuenta, nombres sin prefijo nap_test_, opciones libres y el destino
operativo. NAP_TEST_PORT permite elegir otro puerto local si 55432 está ocupado.
No usar una copia de producción ni apuntar DATABASE_URL a ese servicio.

Desde la raíz se ejecutan por separado las suites infra; backend/pytest.ini no
las recoge:

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/services/tests
```

El modo por defecto bloquea red y procesos reales en infra. Las integraciones
marcadas integration requieren habilitación explícita NAP_INFRA_INTEGRATION=1
y entorno institucional de ensayo; no se habilitan en CI. Desde la raíz,
`docker compose -f docker-compose.test.yml down` detiene y descarta el PostgreSQL
temporal. En entornos restringidos puede ser necesario ejecutar las suites fuera
del sandbox por las restricciones de sockets/threads locales.

Corren sobre SQLite en memoria y con un doble del cliente de Proxmox
(`tests/fakes.py`): **ninguna prueba sale a la red**. La constitución exige
pruebas para todo lo que toque orquestación, máquina de estados o control de
capacidad, con al menos un camino de fallo de infraestructura y un escenario de
concurrencia.

> Ojo con la diferencia de motor: las pruebas usan SQLite y producción
> PostgreSQL. El bloqueo de capacidad es un advisory lock de PostgreSQL y en
> SQLite es un no-op (el motor ya serializa las escrituras), así que la
> exclusión mutua real no es observable desde la suite. Lo que sí se verifica en
> ambos motores es que la contabilidad no pierda ni duplique reservas.

## Modelo de capacidad

Las cátedras **no** tienen un techo de recursos declarado por adelantado. El
control ocurre en la aprobación del pedido, contra la capacidad real del clúster.

Tres piezas sostienen que eso sea seguro:

| Pieza | Qué resuelve |
|---|---|
| **Reserva al aprobar** | Aprobar compromete capacidad en el acto, aunque el contenedor no exista todavía. Sin esto, tres aprobaciones seguidas ven el mismo saldo libre y sobrecomprometen el clúster sin que nadie cometa un error individual. |
| **Token de capacidad** | Detecta que se está confirmando sobre números viejos (la pantalla abierta hace rato, otro admin que aprobó en el medio). Devuelve 409 y obliga a reconfirmar. |
| **Vencimiento de la reserva** | Un pedido aprobado que nunca se despliega retendría capacidad para siempre. A las 24 h se libera sola. |
| **Reversión de la aprobación** | Deshacer una aprobación antes del despliegue y liberar su capacidad en el acto. Sin esto, un error de una cátedra bloqueaba a las demás hasta 24 h, porque la única salida era desplegar el pedido o esperar al vencimiento. |

**Liberar una reserva tiene una sola definición**: `capacidad_service.liberar_reserva()`.
La usan los dos caminos que lo hacen —el vencimiento automático y la reversión
humana— y esa unicidad es deliberada: dos copias podrían divergir, y divergir acá
significa capacidad fantasma, comprometida en la contabilidad y sin nada detrás.

La reversión (`POST /pedidos/{id}/revertir-aprobacion`) es una **operación con
nombre propio**, no un cambio de estado a mano: `PATCH /pedidos/{id}/estado`
sigue rechazando `aprobado → rechazado`, porque mover el estado sin liberar la
reserva es exactamente lo que dejaría capacidad huérfana. Solo alcanza a pedidos
aprobados sin desplegar; una vez que hay servicio, la vuelta atrás es una baja de
servicio. Sus cuatro conflictos —`pedido_no_aprobado`, `despliegue_en_curso`,
`reserva_ya_vencida`, `ya_revertido`— comparten el 409 pero tienen mensajes
distintos, porque para quien los recibe son situaciones distintas.

La reserva **no tiene tabla propia**: un pedido aprobado de tipo `alta` sin
servicio desplegado *es* la reserva. Así no hay dos fuentes de verdad que puedan
divergir, y convertirla en consumo real no es un paso que pueda fallar a medias.

Todo esto vive en `app/services/capacidad_service.py`.

## Recuperación de capacidad

Dos mecanismos complementarios:

- **Vencimiento** (`vencimiento_service.py`) — la vía garantizada. Todo servicio
  nace con fecha de fin conocida por su cátedra. Renovar es pedirlo de nuevo:
  atraviesa el mismo circuito de aprobación, pero **no** reserva capacidad nueva
  (el servicio ya está desplegado y ya cuenta como consumo).
- **Pausado por inactividad** (`inactividad_service.py`) — la vía oportunista.
  Es un heurístico, así que sus defensas importan más que su agresividad: exige
  cobertura mínima de métricas antes de decidir, avisa, y respeta un período de
  gracia. **La falta de datos nunca se interpreta como inactividad.**

Nota sobre la palabra "pausar": en Proxmox, suspender un contenedor congela los
procesos pero mantiene la RAM reservada, y la hibernación real solo es confiable
en máquinas virtuales. Para un contenedor, **detenerlo** es lo que libera CPU y
RAM de verdad; el disco es persistente, así que los datos quedan intactos. Esa
es la mecánica. "Pausado" se conserva como el término de cara a la cátedra
porque describe correctamente lo que percibe.

El almacenamiento **no** se libera al pausar. `GET /servicios/pausados` existe
para que el administrador vea qué sigue ocupando disco.

## Trabajos periódicos

El registro vive en `app/services/scheduler.py` y `app/worker.py`; APScheduler
se inicia exclusivamente en el worker independiente, nunca en el `lifespan`
de la API. Entre los trabajos de mantenimiento están:

| Trabajo | Cadencia |
|---|---|
| `recolectar_metricas` | 15 min |
| `evaluar_inactividad` | 60 min |
| `aplicar_vencimientos` | 60 min |
| `expirar_reservas` | 30 min |

Cada uno es una **función de servicio pura** que recibe una sesión y devuelve un
resumen. El planificador solo la llama con una cadencia, y
`POST /admin/jobs/{nombre}` la dispara a mano por el mismo camino. Eso permite
probarlos sin reloj ni planificador, y degradar a operación manual si el
planificador falla.

Con varios workers, el lock en la tabla `job_locks` impide que se ejecuten por
duplicado. Un lock abandonado (proceso caído a mitad de camino) se recupera a los
30 minutos.

## Convenciones

- La lógica de negocio vive en `app/services/`; los routers **no** invocan
  `proxmoxer` directamente.
- El alcance por cátedra se resuelve **solo** en `app/services/acceso_service.py`.
  Fuera de ahí no debería quedar ninguna comparación directa contra ids de
  cátedra: repetirla es cómo se produce una fuga de datos entre cátedras.
- Toda transición de estado pasa por la función central y queda en el historial.
  El autor puede ser una persona o el sistema (`usuario_id = NULL`); las acciones
  automáticas no se atribuyen a nadie ni se omiten del registro.
- Las bajas son lógicas: el recurso real se libera, el registro permanece para
  reconstruir el consumo histórico.
- Los cambios de esquema se versionan con Alembic; la base no se toca a mano.

## Documentos de referencia

- `.specify/memory/constitution.md` — principios del proyecto (v4.2.0)
- `specs/011-desplegar-servicios-universitarios/` — implementación activa
- `specs/004-unificar-usuario-catedra/` — spec, plan y decisiones de diseño del
  modelo de capacidad vigente


## Ciclo de vida de plantillas y personas (feature 006)

### Plantillas

Una plantilla se puede **corregir** (`PATCH /templates/{id}`) y **retirar** del
catálogo (`{"activo": false}`). Retirar no borra: la plantilla deja de ofrecerse
y no se puede pedir, pero los pedidos y servicios históricos la siguen
resolviendo. `GET /templates/?incluir_retiradas=true` se la muestra al
administrador para que pueda volver a habilitarla.

El `tipo` no es editable: cambiar un LXC por una VM alteraría la naturaleza de lo
que ya se aprobó sobre esa plantilla. Para eso corresponde una plantilla nueva.

Corregir una plantilla **rige de ahí en adelante**. No toca los servicios ya
desplegados, que guardan sus propios recursos, ni los pedidos ya aprobados.

### Regla de oro: el despliegue usa lo reservado

Al aprobar un pedido, el sistema guarda en la propia fila del pedido los tres
números de capacidad que comprometió (`reserva_vcpus`, `reserva_ram_mb`,
`reserva_disk_gb`). **El despliegue arma el contenedor con esos números, no con
los `default_*` de la plantilla.**

No es un detalle de implementación: si el despliegue leyera la plantilla, editarla
entre la aprobación y el despliegue haría que el contenedor naciera con recursos
que nadie aprobó, sobrecomprometiendo el clúster sin dejar rastro. La reserva es
el contrato; la plantilla solo define el punto de partida al pedir.

### Personas

`DELETE /usuarios/{id}` **retira**, no borra sin más. Si la persona dejó
historial —pedidos creados o cátedras a cargo— la cuenta se desactiva y la fila
permanece, porque la autoría de un pedido es parte del historial académico. Si
nunca produjo nada, se elimina de verdad. La respuesta (200, antes 204) dice cuál
de las dos cosas pasó.

Guards, en orden: no retirarse a uno mismo, no dejar al sistema sin
administradores activos, y no dejar cátedras sin responsable. El listado oculta a
las retiradas por defecto; `?incluir_bajas=true` las trae.

El bloqueo por cátedras a cargo **aplica aunque la cátedra esté dada de baja**:
darla de baja no detiene sus servicios, así que sigue necesitando responsable. Es
la razón por la que el mensaje dice "reasignalas" y no "dalas de baja" — lo
segundo no destraba nada.

## Notificaciones por Correo Electrónico (feature 008)

El portal emite notificaciones institucionales automáticas (HTML con identidad UTN FRT y alternativa en texto plano) ante eventos del ciclo de vida de usuarios y pedidos:

1. **Alta de usuario**: Generación automática de contraseña provisoria y despacho de credenciales.
2. **Ciclo de pedidos**: Alerta de nuevo pedido/reenvío a administradores, solicitud de ajuste a docentes, rechazo fundamentado, servicio activo con datos de acceso y errores técnicos de despliegue.

Los avisos se guardan en una cola durable y el worker de notificaciones los
despacha por SMTP. La API no depende de un envío en memoria para confirmar la
acción. Las pruebas usan dobles y bloquean las conexiones reales por defecto.

### Variables de entorno SMTP

| Variable | Tipo | Default | Descripción |
|---|---|---|---|
| `SMTP_HOST` | `str` | `"localhost"` | Host del servidor o relay SMTP institucional |
| `SMTP_PORT` | `int` | `587` | Puerto del servicio SMTP (`587` para STARTTLS, `465` para SSL, `25` para local) |
| `SMTP_USER` | `str` | `""` | Usuario de autenticación SMTP (opcional si relay abierto) |
| `SMTP_PASSWORD` | `str` | `""` | Contraseña de autenticación SMTP |
| `SMTP_FROM` | `str` | `"portal-computos@frt.utn.edu.ar"` | Dirección de correo y nombre remitente |
| `SMTP_TLS` | `bool` | `True` | Habilitar cifrado STARTTLS en la conexión |
| `SMTP_SSL` | `bool` | `False` | Habilitar SSL directo (típicamente puerto 465) |
| `APP_FRONTEND_URL` | `str` | `"http://localhost:5173"` | URL del frontend para enlaces de acceso en los correos |


### Acceso y arranque desde la feature 009

El arranque solo espera la base e inicia la API. Preparar previamente y de forma
explícita el esquema con `alembic upgrade head` y la primera cuenta con
`python -m scripts.bootstrap_admin --actor operador_institucional`. El comando
requiere TTY y contraseña interactiva; si existe cualquier administrador, incluso
inactivo, no lo reemplaza. `seed_admin` delega en ese procedimiento y `seed_dev`
solo prepara una cátedra local, sin cuentas ni servicios publicados.

Configurar claves independientes `SECRET_KEY`, `CSRF_SECRET`, `SECRET_KEYRING`
(JSON con identificadores y claves Fernet), `SECRET_ACTIVE_KEY`, la origin exacta
`APP_FRONTEND_URL` y, si corresponde, `AUTH_ALLOWED_ORIGINS` y
`TRUSTED_PROXY_NETWORKS`. Respaldar el keyring fuera de la base. La migración cifra
factores TOTP confirmados existentes y conserva MFA incoherente para recuperación
asistida. No convertirlo en acceso sin factor. No se acepta un JWT legado sin sid.

API y frontend utilizan la misma origin (`/api/v1`). Vite reenvía `/api` a
`NAP_BACKEND_PROXY`; el navegador no recibe JWT por JSON ni usa perfiles de Web
Storage para acreditar acceso. En HTTPS se usa cookie `__Host-nap_session`
HttpOnly/Secure/Lax. La excepción HTTP `nap_session` solo existe en development.
Las mutaciones exigen Origin y CSRF; login exige también `X-NAP-Request: 1`.

El 2FA es opcional para ambos roles. Si se habilita, se comprueba al ingresar.
La recuperación por código o autorización institucional solo permite reemplazar
el factor; no da acceso al portal hasta confirmarlo. Para el único administrador,
tras verificar identidad fuera del portal, ejecutar en TTY:
`python -m scripts.recuperar_2fa --usuario identificador --actor operador --motivo
"Identidad institucional comprobada" --referencia ACTA-2026-001` (en una línea).
La autorización se muestra una vez, vence en cinco minutos y se consume junto
con la contraseña. No desactiva MFA ni crea otra cuenta.

La bienvenida se registra en la outbox dentro de la transacción de alta. El
worker procesa entregas después del commit, con reintentos, destinatario vigente
 y Message-ID estable. SMTP no configurado no equivale a entrega y nunca registra
el cuerpo. La contraseña provisoria queda cifrada separada del payload, se borra
al entregar o invalidar y se cancela si pasan 24 horas sin entrega. El transporte
SMTP puede duplicar un envío si se pierde la confirmación; Message-ID es estable
 y no se promete entrega exactamente una vez.
