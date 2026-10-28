# NAP: una nube pequeña y simple para la universidad

Propósito acordado: **«un pequeño AWS simple para la universidad»**.
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

## Alcance mínimo y estado real

Un contenedor de aplicación por LXC Ubuntu 24.04 no privilegiado, con recursos,
datos/acceso propios y comprobación antes de entrega. Sin builds desde código,
Docker Compose o software que requiera privilegios/más recursos que los admitidos.
Imágenes privadas usan acceso institucional preparado una vez.

IaaS y Draw.io histórico se conservan. El alta OCI, resolución de imágenes y
runtime genérico están parcialmente construidos; falta el gate Docker definitivo.
El cambio de biblioteca a Docker Hub está especificado y pendiente de T062/T063.
No construir Core/harness ni pilotos Community. Su evidencia previa se conserva
como histórica, sin obligar a repetirla ni habilitar perfiles.

Dos imágenes prueban reutilización: whoami encontrado en Docker Hub y campus-demo
universitaria con persistencia/pull privado. Seguridad, recuperación y consola
siguen siendo parte de la entrega; el laboratorio no acredita el clúster universitario.
