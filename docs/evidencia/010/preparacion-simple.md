# Preparación simple — verificación del 25/10/2026

## Alcance autorizado

El usuario pidió priorizar simplicidad, quitar el ensayo de 24 horas y permitir publicar si funciona o eliminar si falla. La interfaz vigente es elegir aplicación, nombre/descripcion/tamaño, preparar, abrir, confirmar funcionamiento y publicar o eliminar. No se muestran códigos, versiones, perfil de ensayo ni evidencias JSON. La conexión institucional se configura una vez por el responsable técnico.

Se conserva la separación entre oferta reutilizable y las instancias de los pedidos de cátedra. Publicar no elimina la oferta/artefacto; limpia los recursos auxiliares. La vigencia de los pedidos académicos sigue aplicándose. Preparaciones nuevas no tienen vencimiento automático.

## Validación local

- Backend del recorrido simple: **3 passed**; publicación/eliminación, autorización, configuración faltante, reintentos, supervivencia después de 48 horas y persistencia de campos.
- Regresión seleccionada de backend/evidencias: **32 passed**, 39 warnings.
- PostgreSQL aislado, último pase de concurrencia/migración/restauración: **4 passed**, 3 warnings. Dos sesiones simultáneas con claves distintas comparten preparación y reservas; migración conserva historia y elimina plazos activos.
- Frontend: **56 tests**, 14 archivos, aprobados; lint sin errores (advertencias existentes).
- Navegador: **37 passed** en 1,2 minutos, incluyendo roles, recuperación y publicación simple con APIs simuladas.
- Infraestructura: **141 passed, 4 skipped**. Los skips no se consideran aceptación real.
- Contratos: 3 esquemas y 13 ejemplos validados.

Suites: `backend/tests/test_preparacion_simple.py`, `backend/tests/postgres/test_preparacion_simple.py`, `backend/tests/postgres/test_migracion_biblioteca_010.py`, `backend/tests/postgres/test_restauracion_biblioteca_010.py`, `frontend/tests/ensayos.test.jsx` y `frontend/tests/e2e/biblioteca-preparacion.spec.js`.

## Migración del portal local

Antes de aplicar `010_04_preparacion_simple`, se realizó un dump privado completo y se comprobó su restauración en una base aislada. Se compararon los datos protegidos antes/después: **7 usuarios y 24 cátedras sin cambios**. El portal local informa el head `010_04_preparacion_simple` y el backend fue reiniciado. Respaldo e informe privados: `/home/mauro/.local/share/nap009/preparacion-simple-5u1e4d8r`.

La migración sólo quita vencimientos de preparaciones activas y sus operaciones/reservas; no modifica vigencias académicas ni reabre preparaciones cerradas. La limpieza previa de contenedores/pools está documentada en [reparación y limpieza](reparacion-entorno-y-limpieza.md).

## Límite operativo y de evidencia

El entorno local aún no tiene configurados el builder y el perfil de red/preparación institucionales. Consulta real de Draw.io: `sin_preparar`, `puede_preparar: false`; el portal explica que falta completar la conexión con Proxmox. No se instaló ni publicó Draw.io para simular una aceptación.

La comprobación simple utiliza `simple_verification` y verifica procedencia del artefacto, identidades reales, salud registrada y credenciales independientes junto con la confirmación funcional del administrador. No fabrica resultados de reinicio, exportación, aislamiento cruzado o despliegue con proveedor bloqueado. El contrato antiguo conserva sus comprobaciones completas cuando no se usa este marcador. T052/T067/T072/T073 siguen pendientes para infraestructura y mediciones reales; las pruebas con dobles no las cierran.
