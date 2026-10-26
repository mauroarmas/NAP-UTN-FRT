# Contrato de configuración `nap-deployment/1`

Datos internos, no un formulario JSON para administración. Usar modelos discriminados estrictos,
JSON Schema dedicado y hash canónico; no ampliar por excepción `service-definition-1.1` histórico.

## Parte común

| Campo | Regla |
|---|---|
| schema_version | Literal `nap-deployment/1` |
| origen | `imagen_docker` o `community_scripts` |
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
variables reservadas que cambien fuentes, trazas, directorios o política de Core/runtime. Limitar
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

## Origen community_scripts

- Slug e identidad externa `ct/<slug>.sh` para descubrimiento; instalación efectiva es el archivo
  `install/<slug>-install.sh` del paquete certificado, nunca el comando de la ficha ni un URL libre.
- Revisiones/sha256 de instalador, Core, harness, manifiesto de archivos y paquete de política.
- Base OS soportada, variables/respuestas permitidas, dependencias APT/release bloqueadas y hashes,
  configuración posterior tipada, persistencia, acceso y perfil de depuración.
- NAP crea el LXC y conserva marcador de propiedad. El instalador guest no recibe API token,
  credenciales SSH ni acceso a archivos del nodo.
- `FUNCTIONS_FILE_PATH` contiene `lxc/install.func` verificado; Core local con loader cerrado;
  sin build.func/backend host, stdin para preguntas, PTY, telemetría, trazas o personalización que
  borre root password. La política compartida de logs/errores se aplica antes de usar secretos.

Pilotos fijados en la investigación:

| Aplicación | Base | Tamaño inicial | Respuestas y configuración |
|---|---|---|---|
| MariaDB | Debian 13 | Medium | PhpMyAdmin=no; usuario/base por instancia, TLS, clientes y prueba autenticada |
| Caddy | Debian 13 | Medium | xcaddy=no; release exacto/hash, HTTP local y acceso por gateway |

Esos perfiles siguen deshabilitados hasta superar su spike y pruebas reales. No se declara
compatible cualquier `.sh` ni se exige un instalador completo nuevo para otro perfil que satisface
el mismo contrato. Una adaptación de datos/política revisada puede ser necesaria.

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
