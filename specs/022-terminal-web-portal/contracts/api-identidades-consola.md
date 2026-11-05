# Contrato: estado de identidades de consola (administración)

Sólo administración; errores/CSRF/Origin como el resto; mutaciones con `Idempotency-Key`.

| Método y ruta | Resultado |
|---|---|
| `GET /admin/identidades-consola` | 200, lista filtrable por estado: persona (id, nombre), `estado`, `pools_aplicados`, `ultimo_error_seguro`, `reconciliada_at`. **Nunca** la identidad técnica completa ni la contraseña. |
| `POST /admin/identidades-consola/{usuario_id}/reintentar` | 202: marca la persona para reconciliar ya; 409 si está en retiro en curso. |
| `GET /admin/sesiones-terminal` | 200, sesiones abiertas (persona, servicio, nodo, antigüedad, última entrada) sin contenido; permite a administración ver el cupo. |
| `POST /admin/sesiones-terminal/{id}/cerrar` | 202: solicita el cierre (motivo `administracion`). |

La UI muestra estados «Lista», «En preparación», «Con error», «Retirada» y las acciones sólo a administración. La persona de cátedra no ve esta pantalla; sólo recibe «todavía no está habilitado» si su identidad no está lista.
