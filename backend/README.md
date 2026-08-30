# Backend — Portal de Gestión (UTN FRT)

API del portal que media entre las cátedras y la infraestructura (Proxmox VE).
Nadie fuera del portal recibe credenciales de Proxmox ni accede a su interfaz.

## Puesta en marcha

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/alembic upgrade head
./venv/bin/uvicorn app.main:app --reload
```

Documentación interactiva en `/api/docs`.

## Pruebas

```bash
./venv/bin/python -m pytest
```

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

Cuatro, en `app/services/scheduler.py` (APScheduler, arrancado en el `lifespan`):

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

- `.specify/memory/constitution.md` — principios del proyecto (v2.0.0)
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
