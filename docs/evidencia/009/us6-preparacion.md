# US6 — Preparación durable integrada

T095 implementada localmente. `bootstrap_service` delega en `preparacion_service` y el worker puede usar el cliente cerrado; por defecto sigue requiriendo todos los artefactos, perfiles, certificados y runner institucionales. No se habilitó una configuración operativa ni se ejecutó un despliegue real.

La preparación contrasta snapshot aprobado con definición/evidencia inmutables, imagen, receta, mínimos y clúster. Permite terminar una aprobación anterior a un retiro ordinario, manteniendo sus versiones. El bloqueo técnico explícito impide preparar esa versión. Valida disponibilidad y red antes de crear. La configuración institucional de artefactos debe indicar `network_profile_id` expresamente; no se selecciona por posición de una lista.

La aprobación conserva bundle_sha256 y la identidad nueva fija ambos digests. La migración aditiva `009_10_identidad_preparacion` añade definition_sha256/bundle_sha256 nullable a identidades; las históricas quedan sin inventar valores. La descripción PVE nueva incluye clúster/digests y el inventario distingue estrictamente este formato del formato histórico. Ambos se siguen leyendo, pero una identidad histórica incompleta no habilita preparación.

Las contraseñas y APP_KEY se generan una vez, cifradas con contexto de servicio. El commit de credenciales, parámetros congelados y dispatch ocurre antes del transporte, sin mantener una sesión SQL ni locks durante SSH. El mismo mensaje se reenvía al wrapper idempotente para reconciliar, conservando claves y recurso; el wrapper inspecciona antes de repetir efectos. La ausencia de credenciales tras una preparación iniciada produce incertidumbre, sin regenerarlas. El worker vencido no confirma después de un takeover.

`probes_servicio` comprueba operación/recurso, fecha, finalización, probes, dirección inspeccionada y perfil. PostgreSQL exige rol/base de esa instancia; BookStack exige endpoint/docente previstos. No adopta URLs libres del guest. Los endpoints de aplicaciones requieren `network_profiles[ID].instances[resource_uuid]` con host/dirección preparados por infraestructura, coherentes con el registro root del runner. No proporciona IPAM/DNS/CA automáticos. Linux apunta a la ruta de consola autorizada, que sigue bloqueada hasta su gate institucional.

La confirmación local conserva `no_verificada` y pedido `EN_DESPLIEGUE`; no entrega acceso ni genera una notificación de entrega. La evidencia individual y el revelado se integran en T096/T097.

## Verificación

- Preparación/cliente/recuperación/identidad/catálogo/perfiles: **47 aprobadas en 24,14 s**, `/tmp/nap009-us6-preparacion-regresion.txt`.
- Preparación nueva y probes de PostgreSQL/BookStack: **15 aprobadas en 4,87 s**, `/tmp/nap009-us6-preparacion-final.txt`. Incluye takeover durante transporte y denegación de confirmación al worker antiguo.
- Migración desde cero, upgrade histórico y preservación MFA en PostgreSQL 16 aislado: **3 aprobadas en 2,66 s**, `/tmp/nap009-us6-preparacion-migracion.txt`.
- Las cuatro pruebas iniciales de preparación fallaron antes de implementar (`/tmp/nap009-us6-preparacion-red.txt`). La disponibilidad física se sustituye explícitamente; validación de definición/evidencia/snapshot y persistencia/cifrado usan los servicios reales.

Los ensayos usan PVE/runner dobles, excepto PostgreSQL descartable para migraciones. No prueban conectividad, certificados o aplicaciones guest reales. La suite backend completa mantiene su adaptación de contratos históricos para T134; UI de acceso sigue pendiente.
