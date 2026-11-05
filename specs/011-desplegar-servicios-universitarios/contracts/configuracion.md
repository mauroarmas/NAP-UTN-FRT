# Contrato de configuración `nap-deployment/1`

Datos internos, no un formulario JSON para administración. Usar modelos discriminados estrictos,
JSON Schema dedicado y hash canónico; no ampliar por excepción `service-definition-1.1` histórico.

## Parte común

| Campo | Regla |
|---|---|
| schema_version | Literal `nap-deployment/1` |
| origen | `imagen_docker` para nuevas configuraciones |
| modelo_servicio | `paas` o `saas`; etiqueta funcional, no otro mecanismo de ejecución |
| perfil | id, revisión y sha256 de perfil institucional habilitado |
| base | OS, versión, arquitectura, volumen LXC y sha256 comprobados |
| minimum_resources | vCPU/RAM/disco positivos; encaje real en Small/Medium incluyendo sobrecoste |
| access | `web` o `tcp`, puerto principal 1–65535, política y probe tipado |
| variables | Nombres `[A-Za-z_][A-Za-z0-9_]{0,63}`, valores acotados sin NUL; sin claves reservadas del runner |
| secretos | Declaraciones de nombre/etiqueta y modo `generado` o `por_pedido`; nunca valores efectivos |
| persistencia | Lista de destinos absolutos normalizados dentro de la aplicación |

Sólo datos declarados. Prohibir shell/command, Docker flags libres, dispositivos, privileged,
host PID/network, Docker socket, rutas del nodo y volúmenes anónimos no identificados. No permitir
variables reservadas que cambien fuentes, trazas, directorios o política del runtime. Limitar
entradas (20 variables/secretos y 8 destinos por configuración) y tamaño total no sensible a 64 KiB.

Los valores sensibles por pedido se cifran en `SecretoDespliegue`, se referencian por ID/revisión en
el snapshot y se envían sólo por el canal privado del trabajo. Un valor por pedido no se copia a
la oferta. Las credenciales de acceso gestionadas por NAP siempre se generan por instancia.

## Origen imagen_docker

- Referencia normalizada registry/repository y tag original opcional.
- Manifest digest `sha256:…` de plataforma `linux`/arquitectura efectiva; index digest opcional
  y digest de configuración referenciado por ese manifest para correlacionar ImageID en la inspección.
- Perfil de runtime exacto. No inferir la imagen/base a partir de un hostname o texto recibido.
- Puerto y transporte inicial TCP; web usa un upstream local HTTP/HTTPS y borde HTTPS gestionado.
- Conservar ENTRYPOINT/CMD de la imagen; no admitir overrides shell de arranque en esta entrega.
- Imagen accesible en registry autorizado. Resolver tokens sólo en el realm autorizado, validar DNS,
  IP/TLS y no seguir redirecciones de credenciales. Una credencial privada no va en la referencia.
- Declaraciones `Config.Volumes` se convierten en destinos explícitos propios o bloquean el alta.

Se ejecuta con nombre y labels deterministas de identidad/configuración, volúmenes locales dentro
del rootfs LXC, límites de procesos/recursos, política de capabilities y `no-new-privileges` del
perfil. No exponer el daemon. Disable image HEALTHCHECK si su salida no está controlada; el probe
NAP es explícito. Driver de logs `none`; captura inicial por canal privado sin retención cruda.

Medium es el punto inicial conservador del perfil, no garantía de que cualquier imagen quepa.
Small requiere medición adicional. Una app que necesita más de Medium no recibe mínimos ficticios.

## Procedencia de la imagen y compatibilidad histórica

Docker Hub y la referencia propia son dos entradas al mismo `origen=imagen_docker`.
La búsqueda no suministra hashes, perfil ni credenciales confiables: el resolver OCI
vuelve a validar la referencia y fija manifiesto/plataforma. No añadir un segundo
runtime ni campos de scripts/Core para resultados de Docker Hub.

No crear nuevas configuraciones `community_scripts`. Su discriminador ya existe en
esquemas/fixtures de desarrollo: retirarlo del alta y despacho en la implementación,
sin borrar registros, migraciones ni evidencia histórica. Mantener lectura de legado
cuando corresponda y rechazar su ejecución explícitamente. No cambiar el wire protocol
ni aplicar un downgrade destructivo por esta reducción de alcance.

## Acceso y comprobación

- `web`: path relativo de probe (sin esquema, autoridad, query sensible ni redirección externa),
  estados esperados, presupuesto máximo. El gateway sólo contacta el destino del perfil/reserva.
  Borde HTTPS y certificado por instancia; la aplicación escucha detrás del borde en loopback.
- `tcp`: puerto principal y política nativa de autenticación/TLS admitida; probar conectividad y
  la autenticación del perfil cuando exista. Un puerto abierto no prueba todas las funciones.
- Las pruebas de plataforma registran su alcance: conexión, respuesta esperada o función específica.
  No se declara prueba pedagógica o red universitaria a partir de un probe local.

## Disponibilidad de oferta y cambios

La validación automática acredita referencia, estructura, plataforma y perfil habilitado; no una
instalación ya ejecutada. El resultado es `Disponible para solicitar`. El primer pedido sigue las
mismas comprobaciones reales de entrega que los posteriores.

Cambiar imagen, fuente, perfil, variables o persistencia crea revisión inmutable y actualiza sólo
la oferta para decisiones futuras. Pedidos aprobados y renovaciones de instancias existentes
conservan su snapshot. Eliminar una referencia externa produce fallo explícito, no otro contenido.
