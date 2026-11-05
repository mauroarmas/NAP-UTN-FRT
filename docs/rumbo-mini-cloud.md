# NAP: una nube pequeña y simple para la universidad

Propósito acordado: **«un pequeño AWS simple para la universidad»**.
Prioridad aclarada el 28/10/2026: **prototipo académico de prácticas supervisadas**, con
un abanico pequeño de SaaS, PaaS e IaaS y recorridos completos que permitan aprender.
La infraestructura universitaria tendría unos 8 GB de RAM total, CPU antiguas y storage
compartido; verificar estas estimaciones, la arquitectura y la capacidad utilizable antes
de migrar. El laboratorio local sigue siendo un entorno distinto.

**Criterio de cierre acordado:** conexión fiable con Proxmox, interfaces útiles y
gestión completa del recorrido de los recursos autorizados del clúster. La ampliación
del catálogo no condiciona la entrega. Completar primero la integración y demostrar
los servicios existentes con límites y evidencias claros.
Decisión del 27/10/2026: Docker Hub reemplaza a Community Scripts como biblioteca,
y se conservan imágenes propias de las cátedras. Ambas usan el mismo motor OCI.
La implementación sigue en [spec 011](../specs/011-desplegar-servicios-universitarios/cambio-alcance-oci.md).

## Servicios que ofrece

- **Entorno Linux**: plantilla LXC Ubuntu o Debian del nodo; camino IaaS existente.
- **Docker Hub**: buscar una imagen, elegirla y completar datos necesarios.
- **Imagen propia**: ingresar referencia pública o de registry institucional ya
  autorizado. Puede ser software desarrollado por una cátedra.

Las dos entradas de aplicaciones convergen en el mismo formulario y ejecución.
Nombre, imagen y puerto; configuración/persistencia sólo cuando hagan falta.
Sin recetas, UUID, hashes, comandos o trámites de preparar/publicar. Un resultado
del buscador no garantiza encaje en Medium ni funcionamiento de la aplicación.

Se conserva el flujo académico: cátedra solicita aplicación u **Otro**, propósito
y fechas; admin aprueba, rechaza o pide aclaración. Al aprobar reserva capacidad
y despliega desde fecha inicial. Agregar una oferta no instala ni reserva.

## Catálogo y ampliaciones

| Modelo | Servicios elegidos | Estado y objetivo |
|---|---|---|
| IaaS | Ubuntu 24.04 o Debian 13 | Reutilizar el camino existente; basta un sistema en la demostración inicial. |
| PaaS | MariaDB | Configuración PaaS preparada sobre el motor OCI: base y usuario propios, TLS, persistencia y comprobación SQL. Medium en el laboratorio; ver [guía](mariadb-paas.md). |
| SaaS | Draw.io; Memos como ampliación | Draw.io tiene evidencia del laboratorio; Memos queda pendiente para una entrega posterior. |

BookStack queda para una ampliación posterior. Redis se descarta de esta entrega.
Imagen propia mantiene el caso web sencillo y una referencia de imagen publicada;
la carga de archivos, builds y stacks libres quedan fuera del alcance académico.

Orden de trabajo:

1. Cerrar una demostración con los caminos existentes de IaaS y Draw.io.
2. Comprobar inventario de nodos/almacenamiento/plantillas, capacidad y selección de
   destinos autorizados, incluyendo storage compartido sin contabilizarlo varias veces.
3. Cerrar creación, inicio, detención, reinicio, baja y reconciliación: las interfaces
   deben mostrar el resultado observado y conservar el último dato ante errores de consulta.
4. Medir 2–3 instancias simultáneas como objetivo inicial de ensayo, incluyendo el
   consumo del portal y Proxmox; fijar el límite con esos resultados.
5. Repetir el recorrido en infraestructura universitaria una vez configuradas su red,
   certificados, almacenamiento y permisos reales.

El laboratorio real tiene un nodo; las pruebas automatizadas de varios nodos y storage
compartido no equivalen a una aceptación multinodo en la universidad. La migración en vivo,
alta disponibilidad y administración completa de Proxmox quedan fuera del cierre
académico de NAP; el portal gestiona recursos autorizados de las cátedras.

La aceptación consiste en solicitar, aprobar, desplegar, acceder, conservar datos tras
un reinicio y dar de baja liberando recursos. Incluir dos cátedras para comprobar el
aislamiento y un fallo controlado para demostrar diagnóstico y recuperación. No hace
falta mantener encendido todo el catálogo simultáneamente. Documentar los límites y
los resultados forma parte de la entrega académica.

## Motor y estado real

Un contenedor de aplicación por LXC Ubuntu 24.04 no privilegiado, con recursos,
datos/acceso propios y comprobación antes de entrega. Sin builds desde código,
Docker Compose o software que requiera privilegios/más recursos que los admitidos.
Imágenes privadas usan acceso institucional preparado una vez.

IaaS y Draw.io histórico se conservan. MariaDB 11.4 agrega el caso PaaS acotado, con acceso nativo de base de datos. El motor OCI genérico se validó en el
laboratorio con whoami y campus-demo el 28/10/2026; ese resultado no valida otras
aplicaciones ni acredita compatibilidad con el clúster universitario.
No construir Core/harness ni pilotos Community. Su evidencia previa se conserva
como histórica, sin obligar a repetirla ni habilitar perfiles.

Dos imágenes prueban reutilización: whoami encontrado en Docker Hub y campus-demo
universitaria con persistencia/pull privado. Seguridad, recuperación y consola
siguen siendo parte de la entrega; el laboratorio no acredita el clúster universitario.
