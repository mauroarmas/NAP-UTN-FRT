# NAP: una nube pequeña y simple para la universidad

Acordado con Mauro el 26/10/2026: el propósito es **«un pequeño AWS simple para la universidad»**.
Community Scripts debe ser una fuente opcional de aplicaciones, sin limitar el software que una
cátedra pueda necesitar o desarrollar.

## Tres formas de ofrecer un servicio

- **Entorno Linux**: seleccionar una plantilla del nodo (Ubuntu o Debian). Es el camino IaaS existente.
- **Desde la biblioteca**: buscar una aplicación y agregarla cuando NAP tenga una instalación compatible.
- **Aplicación propia**: registrar una imagen preparada por la cátedra o el equipo técnico, independiente
  de Community Scripts. Debe poder reutilizarse para crear instancias separadas de futuros pedidos.

Para aplicaciones propias se propone Docker/OCI como formato habitual. El alta debería pedir nombre,
imagen, puerto y, sólo cuando hagan falta, configuración y almacenamiento persistente. No pedir
manifiestos JSON, hashes, UUID ni recetas al administrador habitual. Los datos técnicos de la imagen
puede aportarlos quien desarrolló el software. Las plantillas LXC de sistemas completos son un
formato distinto y siguen el camino de infraestructura.

Se mantiene el flujo académico: la cátedra solicita aplicación o **Otro**, propósito y fechas;
administración aprueba, rechaza o pide aclaración. Al aprobar se elige Small o Medium, se reserva
capacidad y se despliega desde la fecha inicial. No se reservan recursos por publicar una oferta ni
se asignan cuotas anticipadas a todas las cátedras.

## Motor común, pendiente de implementar

La solución propuesta es un motor de despliegue reutilizable para imágenes de aplicaciones. Debe
resolver instalación, configuración por instancia, acceso, almacenamiento y comprobaciones. Así
agregar otra imagen compatible no requiere programar todo el proceso de nuevo para cada producto.

La biblioteca necesita indicar qué aplicaciones puede desplegar ese motor. Encontrar un script no
lo vuelve compatible: algunos requieren otros sistemas, más recursos o una configuración particular.
La incorporación de imágenes propias ofrece una alternativa para estos casos. Una instancia ya
configurada con contraseñas compartidas no debe convertirse en una plantilla para todas las cátedras.

## Estado real

- Ubuntu/Debian del nodo y el recorrido automático de Draw.io están implementados.
- La biblioteca descubre otras aplicaciones y consulta sus categorías/descripciones públicas.
- Instalar cualquier resultado de Community Scripts **no está implementado**.
- Registrar y desplegar imágenes propias de forma genérica **no está implementado**.

Este documento conserva el objetivo y la propuesta; no acredita esas capacidades pendientes ni crea
una nueva especificación por rutina.
