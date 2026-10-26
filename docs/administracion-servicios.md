# Administración sencilla de servicios

Desde **Catálogo** (`/catalogo`), administración consulta y gestiona las aplicaciones en una sola pantalla. Las cátedras sólo pueden consultar el catálogo y hacer pedidos.

## Agregar una aplicación

1. Pulsar **Agregar servicio**. Elegir una aplicación preparada o **Buscar en la biblioteca** e incorporarla.
2. Completar **Nombre**, una descripción opcional y **Small** o **Medium**. Pulsar **Preparar aplicación**.
3. Cuando aparezca **Ya podés probarla**, pulsar **Ver acceso**, abrir la aplicación y comprobar que funcione. Elegir **Funciona correctamente** o **No funciona, eliminar**.
4. Si funciona, pulsar **Publicar servicio**. Quedará disponible para los pedidos de las cátedras.

NAP se ocupa de la preparación técnica. Se puede cerrar la ventana y retomarla después. No hay que introducir entornos, códigos, versiones ni documentos técnicos. La preparación no vence a las 24 horas; la publicación permanece hasta que administración la retire. Si falla la preparación, se puede eliminar y comenzar otra vez.

Publicar conserva la aplicación preparada para reutilizarla y libera los recursos auxiliares de preparación. Cada pedido aprobado tendrá su propia instancia y sus propios datos. Retirar una oferta impide nuevos pedidos y conserva los existentes.

La biblioteca permite descubrir aplicaciones; sólo las que cuentan con una preparación compatible pueden instalarse desde NAP. Draw.io es el piloto disponible en esta integración. Incorporar una ficha no significa que ya esté instalada.

## Conexión inicial

El responsable técnico debe dejar configurada la conexión institucional con Proxmox, la construcción de aplicaciones y la red una sola vez. Cuando falta esa configuración, NAP lo indica y deshabilita la preparación. Administración no tiene que adivinar ni escribir identificadores técnicos en cada alta. Ver [conexión de infraestructura](conexion-infraestructura.md).

## Dos tamaños

| Tamaño | CPU | Memoria | Disco |
|---|---:|---:|---:|
| Small | 1 vCPU | 512 MB | 4 GB |
| Medium | 2 vCPU | 1024 MB | 8 GB |

Ambos utilizan la base Linux institucional Ubuntu 24.04 en LXC. Un tamaño insuficiente para la aplicación aparece deshabilitado. Si ninguno alcanza, debe revisarse su preparación o la capacidad disponible.

## Pedido y aprobación

La cátedra elige la aplicación, explica su propósito pedagógico e indica las fechas. No elige hardware. Se conserva **Otro** para necesidades aún no disponibles.

Administración elige el servicio y Small o Medium, evalúa la capacidad y aprueba, rechaza o pide una aclaración. Aprobar reserva los recursos; después se despliega desde la fecha inicial. Las fechas académicas del pedido siguen vigentes: son independientes de la permanencia de la aplicación en el catálogo.

Cambiar una recomendación no modifica pedidos ya aprobados. Las renovaciones mantienen sus recursos originales.

## Pruebas manuales

- Como administrador, abrir **Catálogo → Agregar servicio**: comprobar que sólo se pidan nombre, descripción y tamaño. No debe haber entorno de prueba, plazo de 24 horas ni opciones técnicas avanzadas.
- Con infraestructura configurada, preparar Draw.io, cerrar y volver a abrir la ventana: debe recuperar el progreso sin crear otra preparación.
- Abrir la aplicación, crear y guardar un diagrama. Confirmar que funciona y publicar. Debe aparecer en **Servicios disponibles**.
- En otra preparación, elegir **No funciona, eliminar**: debe mostrar la eliminación y permitir comenzar de nuevo cuando termine.
- Sin infraestructura configurada, debe aparecer un mensaje claro y no deben crearse recursos.
- Como cátedra, comprobar que se pueda pedir una aplicación publicada o **Otro**, con justificación y fechas, sin herramientas administrativas.
- Retirar una oferta: debe impedir nuevos pedidos y conservar los ya aprobados.

Las pruebas que crean aplicaciones requieren la infraestructura conectada. Las comprobaciones automatizadas con simuladores no sustituyen ese recorrido real.
