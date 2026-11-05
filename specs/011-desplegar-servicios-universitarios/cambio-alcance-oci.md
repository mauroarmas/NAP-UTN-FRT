# Decisión de alcance — 27/10/2026

**Solicitada y aprobada por Mauro**: retirar Community Scripts para acelerar la
entrega. Docker Hub pasa a ser la biblioteca; se mantiene agregar imágenes propias.
No iniciar una spec nueva, repetir planificación desde cero ni reimplementar el motor.

## Recorrido vigente

**Docker Hub (buscar y seleccionar)** o **Imagen propia (ingresar referencia)**
→ mismo formulario breve → misma validación/configuración `imagen_docker`
→ oferta disponible sin CT/reserva → pedido → aprobación/reserva
→ despliegue Docker dentro del LXC → comprobación/acceso/aviso.

Imágenes propias pueden alojarse en Docker Hub u otro registry público/institucional
autorizado. No es un segundo runtime. NAP no construye imágenes desde código ni
orquesta conjuntos Compose. Una ficha no acredita compatibilidad ni instalación.
IaaS sigue ofreciendo las plantillas LXC Ubuntu 24.04/Debian 13; no se reemplazan
por imágenes OCI de sistemas operativos.

## Recorte concreto de tareas

| IDs | Decisión |
|---|---|
| T006 | Spike Community ya completado históricamente; retirado del conjunto activo. Conservar evidencia, no repetir. |
| T052–T053 | Retiradas: pruebas específicas de harness y perfiles Community. |
| T055–T061 | Retiradas: empaquetado Core/scripts/locks, harness, perfiles MariaDB/Caddy, acceso específico y estrategia/gate Community. |
| T051/T054 | Adaptadas a búsqueda/API/UI Docker Hub y rechazo de nuevas ejecuciones Community. |
| T062/T063 | Adaptador Hub y UI sobre alta OCI existente; retirar proveedor anterior de navegación/altas/despacho sin borrar historia. |
| T064 | Aceptación del descubrimiento Hub; reutiliza la validación del motor T050. |
| T076/T086/T087/T098/T103 | Un único motor y dos imágenes, no doble aceptación por dos estrategias. |

Los IDs originales se preservan. **37/95 tareas activas verificadas, 58 pendientes**,
frente a 38/105 antes: diez retiradas, una de ellas ya completada. No hay nuevas
tareas completadas por editar documentos. Son nueve tareas pendientes menos y
menos ensayos físicos; el número de tareas no estima horas restantes.

## Aceptación simplificada

- **whoami**, descubierto en Docker Hub: búsqueda, alta, pedido y acceso.
- **campus-demo**, imagen propia: mismo motor, dato persistente y descarga privada.
- Dos cátedras aisladas, reserva atómica, datos/credenciales propios, consola de
  lectura, recuperación y baja comprobadas. No duplicar la batería del motor por
  entrar a la misma referencia desde otro botón.
- Categorías del proveedor sólo si están disponibles; búsqueda por nombre basta.
  Ante fallo/rate limit, reintento o ingreso de referencia, sin caché/espejo nuevo.

Se retiran los pilotos obligatorios MariaDB/Caddy y la exigencia de cuatro apps.
**Caddy interno del borde HTTPS del runtime se conserva**: es infraestructura
Docker ya diseñada, no el perfil Community de una oferta de catálogo.
Acceso TCP conserva sus contratos/guardas de T034/T036/T046 cuando se declara;
no debe convertirse en un puerto abierto sin autenticación ni presentarse como
entregado mientras su política no esté comprobada.

## Continuidad y siguiente paso

Esta modificación es de especificación/plan/tareas/contratos/traspaso; **el cambio
de proveedor en el código y la UI todavía corresponde a T062/T063**. No afirmar
que Docker Hub ya reemplazó la búsqueda instalada por cambiar estos documentos.
La corrección de `net0.type=veth` sigue pendiente de distribuir y el gate Docker
definitivo debe completarse; el recorte no habilita perfiles automáticamente.

Preservar migración 011 aplicada, datos, discriminadores legacy necesarios,
recibos/spikes e IaaS/Draw.io. No eliminar su historia ni convertir un origen
antiguo en OCI inventando una imagen. Las configuraciones Community nuevas deben
rechazarse en alta y despacho, manteniendo lectura histórica si corresponde.

La constitución 4.2.0 no exige Community Scripts; conserva oferta/instancia y
seguridad sin cambios. Documento rector funcional: [spec.md](spec.md); ejecución:
[tasks.md](tasks.md); compañero: [traspaso](../../docs/traspaso-011.md).
