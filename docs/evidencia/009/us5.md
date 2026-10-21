# US5 — Calendario, formularios y cobertura por períodos

Fecha de verificación: 2026-10-20. Rama `009-remediar-hallazgos-cierre`. Pruebas locales aisladas; no se desplegó infraestructura real ni se migró una base operativa.

## Comportamiento comprobado

- Calendarios por año con revisión, modalidades ausentes explícitas y control de conflicto. Dos años independientes; una corrección conserva los períodos ya aprobados. La UI preserva el borrador ante 409 y exige recargar la revisión.
- Fechas institucionales inclusivas convertidas a intervalos UTC con fin exclusivo. La aprobación futura retiene capacidad desde ahora; su reserva vence a las 24 horas del inicio, limitada por el fin autorizado. Antes del inicio se rechaza desplegar y no hay activación automática.
- Solicitud y reenvío envían una vigencia completa. Cambiar modelo limpia plantillas incompatibles; cambiar modalidad elimina fechas anteriores. Reabrir reinicia el formulario. Docente consulta ajustes sin botones de cancelar/reenviar; administración realiza la corrección.
- La evaluación corresponde a la selección actual. Editar recursos, destino o fechas invalida el token. Sobreasignar exige justificación; 409 conserva recursos, fechas y motivo y obliga a reevaluar. Se retiró la aprobación directa con valores implícitos.
- Renovar conserva identidad, recursos, producto histórico y datos. Una plantilla retirada o cuyo modelo actual cambió no sustituye el producto aprobado. La modificación de un período crea otro pedido con motivo; la aprobación sustituye una sola revisión sin borrar historia.
- Una renovación pendiente o futura no cubre un receso. La pausa se confirma antes de liberar CPU/RAM y conserva disco. Durante el intervalo no se puede reactivar; llegado el inicio, se vuelve a comprobar capacidad. Una renovación aprobada antes del envío cancela una pausa de vencimiento que dejó de corresponder.
- Los GET incluyen operaciones, períodos autorizados, cobertura, próximo inicio, confirmación y acciones permitidas mediante consultas agrupadas. La UI recupera seguimiento, bloquea acciones incompatibles y distingue renovación registrada de contenedor encendido. Un ledger incierto no ofrece inicio. PATCH `vence_at` devuelve 422.
- Los listados ordinarios no serializan credenciales ni enlaces heredados. La preparación y entrega de acceso tipado corresponden a US6.

## Resultados

| Verificación | Resultado | Registro local |
|---|---|---|
| Backend: calendarios, payloads, operaciones, proyecciones y efectos simulados | 23 aprobadas, 18,51 s | `/tmp/nap009-us5-resume-backend-final.txt` |
| PostgreSQL 16: períodos/renovación/concurrencia y migraciones | 8 aprobadas, 17,37 s | `/tmp/nap009-us5-resume-postgres.txt` |
| Frontend: suite de componentes | 17 aprobadas, 6,76 s | `/tmp/nap009-us5-frontend-final.txt` |
| Chromium: suite de recorridos, incluida SPA compilada | 9 aprobadas, 14,2 s | `/tmp/nap009-us5-browser-final.txt` |
| Lint | Sin errores; 10 advertencias de hooks/exportaciones existentes | `/tmp/nap009-us5-lint-final.txt` |
| Diferencias | `git diff --check` sin errores | Verificación local |

Se observaron primero fallos de regresión por operación ausente en pedidos, botón de inicio ofrecido con ledger incierto y renovación dependiente del catálogo actual. Los casos pasan tras corregir esas condiciones. Chromium se descargó de nuevo porque su instalación temporal anterior no estaba disponible; ese fallo inicial de entorno no acredita un fallo funcional.

Comandos desde `backend/`:

```bash
./venv/bin/python -m pytest -q tests/test_proyecciones_vigencia_009.py tests/test_operaciones_contrato_009.py tests/test_calendario_vigencias_009.py tests/test_payloads_009.py tests/test_operaciones_efectos_009.py
TEST_DATABASE_URL=postgresql+asyncpg://nap_test:nap_test_local_only@127.0.0.1:55432/nap_test_009 ./venv/bin/python -m pytest -q tests/postgres/test_renovacion_periodos_009.py tests/postgres/test_migracion_base_009.py
```

Desde `frontend/`: `npm test -- --run`, `npm run lint` y `PLAYWRIGHT_BROWSERS_PATH=/tmp/nap009-playwright npm run test:e2e`.

## Límites y trabajo posterior

PostgreSQL utiliza esquemas aleatorios descartables del compose de pruebas; los ensayos de períodos conservan registros y estados entre solicitudes y decisiones concurrentes. Los recorridos de navegador utilizan dobles HTTP y reloj controlado para el receso. No acreditan acceso desde una red académica ni preparación real de invitados.

El bundle principal todavía genera una advertencia de tamaño; carga diferida y rendimiento corresponden a US7. Las pruebas heredadas de backend aún deben adaptarse a los contratos nuevos en T134: no se declara aprobada la suite completa. Los avisos de vencimiento quedan registrados y deduplicados; su entrega por outbox se completa en T110. La preparación real continúa bloqueada hasta implementar US6.
