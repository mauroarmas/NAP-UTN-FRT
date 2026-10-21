# Reasignación y revocación de consola nativa

Diseño objetivo para FR-001–FR-003/FR-052 y SC-001. La consola es la excepción de infraestructura autorizada por la constitución y requiere identidad PVE individual limitada a pools de cátedras actuales. Nunca usar identidad PVE compartida entre titulares. El control NAP y el control nativo se validan por separado.

## Gate de infraestructura

Antes de habilitar consola, infraestructura inventaría identidad por usuario, ACL directas y heredadas/grupos, pools y sesiones; demuestra en la versión real del clúster cómo retirar los permisos afectados y terminar conexiones/tickets ya abiertos. Se documenta ejecutor institucional, procedimiento y ensayo negativo reproducible. El importador institucional `scripts.importar_identidades_consola` registra usuario NAP, identidad PVE individual y referencia de la comprobación, con actor obligatorio; ausencia de dato queda desconocida, no equivale a sin acceso. El campo no es editable desde PATCH de usuario. No se reemplaza un vínculo asignado sin revocar la identidad anterior. Retirar una ACL o esconder un enlace por sí solo no demuestra terminar una consola activa. Si no existe un procedimiento que lo logre, consola permanece deshabilitada: no se supone una API de terminación soportada.

La ejecución de ACL/sesiones corresponde al operador institucional mediante herramientas autorizadas del clúster; el portal coordina y audita el trámite. No se añade un ejecutor de administración general ni nuevos comandos al guest-runner. El operador comprueba también permisos efectivos heredados y caminos directos; eliminar solo una ACL visible no basta.

## Protocolo duradero

1. Admin solicita reasignación, retiro/desactivación o cambio de rol mediante las rutas actuales de `/catedras` o `/usuarios`, con revisión esperada e Idempotency-Key. Si reduce acceso nativo, una transacción crea `cambios_acceso_consola`, fija alcance anterior/propuesto, bloquea operaciones NAP sobre ese alcance y devuelve 202 con `cambio_consola_id` y Location. Retiro/desactivación/cambio de rol bloquea toda operación de dominio de la cuenta y revoca sesiones NAP al admitir el trámite, incluso si intenta autenticarse nuevamente mientras está pendiente. La consulta mínima de estado de cuenta y logout no levantan ese bloqueo. No se cambia todavía titularidad/rol/actividad ni se habilita al nuevo titular. Sin identidad nativa, solo se permite finalizar localmente cuando el inventario institucional acredita que nunca tuvo tal acceso; mapeo desconocido bloquea con 409.
2. El operador recibe los datos del trámite desde el panel administrativo. Retira todos los permisos efectivos afectados y termina las sesiones/conexiones anteriores de la identidad PVE; si debe invalidar todas, restablece únicamente los pools que siguen autorizados, nunca el retirado. Prueba una consola ya abierta y una URL/ticket guardados: acceso retirado denegado. Con una sesión nueva comprueba los otros pools legítimos; si no quedan, acredita que no existe ninguno permitido. Retiro/desactivación no conserva pools. Conserva referencia institucional sin tickets ni cookies.
3. Admin importa evidencia `revocacion_consola` en `POST /evidencias` y confirma el trámite con esa referencia. Esta declaración manual auditada no sustituye las pruebas reales del gate. El backend contrasta hash, tipo, identidad, scopes, revisión y fecha posteriores a la solicitud; no vuelve a permitir URLs/credenciales libres ni ejecuta código del artefacto.
4. Una transacción con locks de filas y el lock administrativo cuando corresponda revalida el estado y último administrador, aplica el cambio propuesto, historia, evidencia e idempotencia, y marca completado. Solo entonces habilita el acceso NAP del nuevo titular y libera los bloqueos restantes. La concesión de consola al nuevo titular es también institucional y solo sobre sus pools efectivos; no se entrega un ticket antes de la confirmación. Historial académico conserva sus autores anteriores.

Cambios incompatibles sobre un mismo usuario/cátedra se rechazan con 409. Se comprueba revisión tanto al admitir como al completar; no se mantiene transacción durante intervención externa. La protección del último administrador cuenta también los retiros/degradaciones pendientes al admitir un trámite, para no bloquear simultáneamente a todos los administradores. Se vuelve a comprobar al completar. Si se detecta deriva, no se aplica un cambio parcial; se informa 409 y se exige resolver el trámite vigente, sin restaurar automáticamente permisos externos retirados.

Fallo o incertidumbre del operador: registrar motivo seguro mediante la interfaz de resultado, mantener bloqueo NAP y titularidad anterior sin transferencia; estado `revocacion_fallida` sigue abierto y admite reintento/evidencia nueva. No anunciar cuenta retirada o cátedra reasignada como resultado completado. Mientras siga pendiente, sus recursos no se entregan a terceros; el acceso nativo anterior sigue perteneciendo al titular anterior hasta que el operador lo termine. El estado explícito permite continuar otros trabajos sin atribuir una revocación no comprobada.

## Interfaces de seguimiento

Todas admin operativo; errores/CSRF/Origin como auth.md. Mutaciones requieren Idempotency-Key.

| Método y ruta | Resultado |
|---|---|
| `GET /admin/cambios-consola` | 200, lista filtrable por estado con alcance y motivo seguro; sin secretos. |
| `GET /admin/cambios-consola/{id}` | 200, estado, revisión, identidad, scopes anteriores/propuestos, instrucciones y evidencia si existe. |
| `POST /admin/cambios-consola/{id}/registrar-fallo` | 200, motivo institucional obligatorio; conserva bloqueo y trámite abierto. |
| `POST /admin/cambios-consola/{id}/confirmar-revocacion` | 200, cuerpo `{ "evidencia_ref": "UUID" }`; solo evidencia válida del trámite/revisión actual completa el cambio. |

Una revisión desactualizada devuelve 409; evidencia inválida 422; docente propio/ajeno 403. La UI muestra Pendiente de revocación / Revocación fallida / Completado y acciones solo admin. La identidad o URL de consola no se toma del solicitante: resuelve el recurso autorizado y bloquea trámites pendientes antes de emitir un enlace.

Aceptación: dobles prueban orden bloqueo→revocación acreditada→transferencia, fallo/reinicio/replay y conflicto concurrente. Integración real mantiene abierta una consola previa, retira acceso y prueba tanto esa conexión como la URL guardada y el pool legítimo restante. No marcar completado el gate real por un test con dobles.
