# Contrato de acceso y presentación

## Catálogo y formularios

- Una sola pantalla Catálogo para administración y ofertas solicitables para cátedra.
- «Agregar servicio» ofrece «Desde la biblioteca» y «Aplicación propia». Los entornos Linux
  existentes se conservan, sin obligar a agregarlos otra vez por estos caminos.
- Imagen propia: nombre, imagen y puerto. Descripción, modelo funcional, variables, declaraciones
  de secretos y persistencia sólo cuando sean necesarios; no pedir infraestructura, scripts,
  manifests, hashes o certificados. Secretos efectivos se completan por pedido cuando hagan falta.
- Biblioteca: búsqueda, categorías del proveedor, datos disponibles y razón de incompatibilidad.
  Una elección compatible abre el mismo formulario breve. No hay «Guardadas», pantalla de versiones,
  entorno de ensayo, confirmar funcionamiento o publicar manualmente.
- Alta correcta significa «Disponible para solicitar». No usar «Aplicación instalada» hasta la
  entrega de una instancia. Un error conserva valores válidos y permite reintentar.
- La cátedra conserva aplicación/propósito/fechas y «Otro». Referencia opcional de imagen propia
  describe software; nunca pregunta hardware, VMID o datos internos de Proxmox.

## Pedido, servicio y consola

- Etapas reales y último avance, con acción administrativa «Ver consola» en detalle de pedido y
  operación del servicio. Estados separados para espera, instalación, comprobación, consulta
  interrumpida, incertidumbre, error y entrega.
- Consola de sólo lectura: fondo `#000`, texto `#fff`, fuente monoespaciada, selección normal,
  desplazamiento y navegación por teclado. No xterm, contenido HTML ni interpretación ANSI/OSC.
- Seguir mensajes nuevos por defecto. Si se revisan los anteriores, pausar desplazamiento y
  mostrar cantidad de mensajes nuevos; permitir volver al final. Renderizar una ventana acotada
  de texto y cargar páginas anteriores, sin montar 10 MB de nodos DOM al abrir.
- Mostrar operación/intento efectivo y fases; un fallo de consulta no cambia el resultado del
  instalador. Silencio significa «Sin mensajes recientes», no una animación de trabajo inventada.
- Copiar/descargar sólo a pedido explícito; usar el registro depurado retenido con aviso de recorte
  o vencimiento. No almacenar texto en localStorage/caché ni copiar automáticamente secretos.
- Cerrar panel no cancela proceso; recuperar ventana consulta el mismo estado e intento.
- Las cátedras ven resumen y resultado de lo propio, sin consola de instalación. La consola
  interactiva IaaS existente es otra acción y conserva su autorización específica.

## Acceso web genérico

Conservar adaptador Draw.io actual. Añadir uno genérico: no forzar BasicAuth interno, parámetros
Draw.io, HTML esperado de Draw.io ni eliminación de cookies de cualquier aplicación.

- Origen HTTPS distinto por servicio, fuera del origen del portal/API. Reusar apertura NAP por
  código de un uso y cookie `__Host-nap_app`; autorizaciones actuales en cada petición.
- Perfil de red fija IP, Host/SNI y CA; TLS hacia borde de instancia y hacia navegador, sin URLs
  de destino suministradas por cliente. La aplicación se publica detrás del borde en loopback.
- Métodos HTTP GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS; redirecciones sólo al origen correspondiente,
  límites de carga/descarga explícitos, streaming acotado y sin buffering ilimitado.
- Conservar cookies/autenticación nativas de la aplicación. Reservar nombres NAP; quitar cookies
  del portal/gateway antes del upstream y no reutilizar cookie jar compartido de HTTPX. Cookies
  emitidas por aplicación sólo para su host; no aceptar dominio hermano/padre ni sobrescribir NAP.
- WebSocket: admitir sólo si el perfil de aplicación lo declara; verificar sesión/origen antes del
  upgrade y revalidar cada 5 s mientras dure, cerrando al perder autorización. No seguir redirects
  ni cambiar destino fuera del perfil. Este tráfico pertenece a la aplicación; nunca se reutiliza
  para convertir la consola de instalación en un canal de escritura o terminal del nodo.
- Sin service workers: podrían responder desde caché después de revocar la sesión. No borrar
  indiscriminadamente datos del navegador para imponer la política.

Esto controla acceso a la aplicación, no crea usuarios dentro de software arbitrario. Su login
propio continúa existiendo si la imagen lo requiere. Un HTML o conexión exitosa se registra como
la comprobación realizada, no como prueba de toda la función pedagógica.

## Acceso nativo TCP

Dirección, puerto, TLS y credenciales sólo para administración y responsable vigente; la conexión
usa la autenticación de la aplicación y las redes permitidas. Para MariaDB se configuran usuario y
base independientes y transporte TLS obligatorio. No mostrar contraseña de root del nodo ni usar
cuentas compartidas entre cátedras.

No prometer que cerrar NAP finaliza conexiones TCP previamente establecidas, ni inferir usuarios
en cualquier imagen. La política declarada debe tener configuración de credenciales y permisos
por instancia cuando corresponda; un puerto abierto sin ese control no equivale a entrega segura.

## Pruebas de interfaz

Validar con Vitest y navegador: ambos formularios sin campos internos; imágenes/fuentes rechazadas
con datos conservados; sólo admin ve consola; reabrir no crea otra operación; scroll pausado;
cursor repetido sin duplicación; logs enormes/recortados/vencidos; contenido malicioso literal;
revocación durante lectura/exportación; acceso web por origen propio y flujo IaaS/Draw.io intactos.
Las pruebas visuales con backend simulado no acreditan Docker ni Community Scripts reales.
