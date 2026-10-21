# Regresión general preparatoria — T134 pendiente

Fecha: 2026-10-21. La suite completa **todavía no aprueba**. Estas corridas anticipan la adaptación de pruebas heredadas; no completan T134, SC-008 actualizado ni la aceptación de infraestructura. No se ejecutaron transportes reales de PVE/SMTP durante pytest.

| Corrida | Resultado | Alcance |
|---|---|---|
| Base completa con límite de 20 fallos | 166 aprobadas, 19 fallidas, un error; 198,28 s | Se detuvo antes de recorrer toda la colección |
| Siguiente tramo, posterior a autorización | 82 aprobadas, 20 fallidas; 42,63 s | Capacidad y despliegue todavía usaban contratos anteriores |
| Tramo posterior a despliegue | 171 aprobadas, 30 fallidas; 135,09 s | Se detuvo en notificaciones de pedidos; quedan archivos posteriores por recorrer |
| Nueve módulos heredados adaptados | 73 aprobadas; 54,12 s | Aislamiento, ajustes, alta de usuarios, autorización, aprobación, capacidad y despliegues |
| Worker PostgreSQL corregido | Cuatro aprobadas; 6,66 s | Fencing, corte tras POST, reclamación concurrente y consulta durante I/O |

Las corridas tienen cobertura superpuesta: no sumar sus cantidades como si fueran una suite única aprobada.

Cambios de pruebas: cuerpos cerrados con vigencia e idempotencia, evaluación explícita por POST y token ligado a pedido, alta de usuario con contraseña generada/email válido, ledger en vez de campos retirados, HTTP 202/worker/UPID y asignación congelada. Las cantidades de los ensayos cumplen los mínimos de la definición. La sobreasignación con motivo respeta los límites físicos; un diccionario de opciones arbitrarias se rechaza. Ninguna adaptación flexibilizó esos controles del backend.

La reclamación concurrente PostgreSQL tenía una fixture sin `asignacion` después de introducir digests de definición/receta. Su `gather` abandonaba tareas al primer error y llegaba a un deadlock al borrar el esquema de prueba. Se completó el contexto tipado y se esperan todos los resultados antes de afirmar éxito o terminar la prueba; cuatro pruebas del módulo aprueban.

## Pendientes conocidos

- `test_historial_reversion.py`: idempotencia/evaluación actuales y caducidad del ledger.
- `test_inactividad_pausado.py` y `test_inactividad_sin_metricas.py`: intervalos confirmados, deltas/cobertura/frescura y admisión/confirmación por worker; fixtures antiguas no acreditan esa telemetría ni propiedad.
- `test_job_locks.py`: registro completo de trabajos nuevos.
- `test_liberar_reserva.py`: única autoridad de capacidad y caducidad; no columnas retiradas.
- `test_pedido_creation.py`, `test_pedido_sin_cuota.py`: vigencia explícita, perfil publicado e idempotencia; los servicios SaaS ya no se solicitan como descripción libre sin perfil.
- `test_notificaciones_preferencias.py` y `test_pedidos_notificaciones.py`: comprobar el contrato actual y el outbox, sin asumir envío SMTP dentro del HTTP. Revisar particularmente creación/reenvío/transiciones de pedido: `solicitud_service.crear` y `pedido_service.transicionar` no llaman actualmente a un encolador de avisos de pedido. Antes de atribuir todos los fallos a fixtures, determinar qué avisos se deben conservar e implementar los que falten con deduplicación y destinatarios actuales.
- Archivos posteriores a `test_pedidos_notificaciones.py`: aún no recorridos en esta etapa. Repetir al final la colección completa, frontend, navegador y SC-008 con el código final.

Logs locales: `/tmp/nap009-suite-cierre-base.log`, `/tmp/nap009-cierre-grupo2-base.log`, `/tmp/nap009-cierre-grupo3-base.log`, `/tmp/nap009-cierre-legacy-adaptado.log` y `/tmp/nap009-cierre-worker-pg.log`. No son evidencias de aceptación PVE ni sustituyen el ensayo con el único responsable de cátedra.
