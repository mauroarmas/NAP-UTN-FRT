# Administración de instancias — 28/10/2026

Se corrigió la proyección de acciones, la sincronización del estado y la reconciliación
de detenciones sin UPID. Se mantiene la comprobación de identidad y pool, la exclusión
entre operaciones, la retención de disco al detener y la baja exclusiva de administración.

## Observación real del laboratorio

Mediante la API configurada del Proxmox local se comprobó la marca de propiedad, el pool
y el estado de las tres instancias existentes:

| VMID | Servicio | Estado real y final de NAP |
|---|---|---|
| 100 | Draw.io | Detenido |
| 101 | Redis | Encendido |
| 102 | MariaDB | Encendido |

Redis y MariaDB figuraban detenidos e inciertos. La sincronización verificó su identidad,
configuración y estado; actualizó los compromisos y habilitó detener, reiniciar y dar de baja.
Draw.io tenía una detención pendiente sin UPID; después del plazo de espera, el ejecutor
verificó que estaba detenido y sin bloqueo en Proxmox, y cerró la operación por observación.
No se reenvió la orden ni se eliminó ninguna de estas instancias.

## Cierre de integración e inventario

Por indicación de Mauro, la entrega académica prioriza conexión, capacidad y operación
de Proxmox e interfaces útiles; las aplicaciones adicionales pasan a ampliaciones futuras.
Se repitieron consultas de sólo lectura al laboratorio: conexión con verificación TLS,
inventario del nodo `proxmox` (4 CPU, aproximadamente 8 GB de RAM), almacenamiento
`local`/`local-lvm`, plantillas Ubuntu/Debian y panorama de capacidad. Este último confirmó
el destino autorizado `proxmox` / `local-lvm` con los compromisos existentes.

El panel Inicio permite actualizar el estado y consulta cada 30 segundos mientras está
visible. Distingue una consulta fallida de un valor cero, conserva los últimos datos y
presenta el almacenamiento compartido una sola vez, con los nodos que lo ven. Los discos
locales homónimos se mantienen separados por nodo.

Validación focalizada: 52 pruebas backend de inventario, capacidad, evaluación, bases
IaaS, estado observado, transporte y reconciliación; 16 pruebas de interfaz de este bloque;
compilación del frontend aprobada. Los escenarios multinodo/storage compartido se probaron
con dobles: el laboratorio real tiene un único nodo. La conexión y aceptación del clúster
universitario, con su red, almacenamiento y permisos, siguen pendientes.

## Validación automatizada

Pruebas focalizadas de proyección, ciclo de vida, recuperación y efectos de operaciones;
pruebas nuevas de sincronización, identidad ajena, errores de consulta, exclusión de operaciones
y detención sin envío cuando ya está apagado. Interfaz verificada con Vitest y diez recorridos
Playwright de acciones y operaciones. Los dobles de estas pruebas no acreditan una eliminación
real en Proxmox; no se probó la eliminación de las instancias existentes.

## Ensayo real del ciclo IaaS de cierre

Se creó una instancia técnica independiente de Ubuntu 24.04 Small (1 vCPU, 512 MB,
4 GB) mediante los servicios normales de solicitud, evaluación, aprobación y ejecución
de NAP contra el Proxmox local. Trazabilidad: pedido **39**, servicio **21**, VMID **101**.
El VMID se reclamó disponible y se comprobó su identidad y pool antes de cada acción;
el recurso del ensayo no corresponde a la instancia histórica que usó antes ese número.

| Comprobación real | Resultado |
|---|---|
| Solicitud, reserva y creación | Operación confirmada; LXC propio en ejecución. |
| Acceso inicial | Credenciales recuperadas por el recorrido autorizado, sin imprimirlas. |
| Detención | Estado stopped confirmado; CPU/RAM liberadas y disco retenido. |
| Nuevo inicio y reinicio | Ambas operaciones confirmadas; misma identidad de volumen raíz. |
| Baja | Ausencia de contenedor y volúmenes confirmada; identidad retirada, baja lógica y compromiso liberado. |
| Capacidad posterior | Recuperó el saldo anterior al ensayo. |
| Avisos de prueba | Sólo portal; se comprobó que no se encolaron correos para la cátedra técnica. |

El recibo y el ejecutor del ensayo quedan fuera del repositorio, en el directorio privado
`nap011/cierre-iaas`. La pausa temporal del worker durante el ensayo permitió ejecutar
las operaciones en el proceso de verificación con avisos sólo de portal; el worker normal
quedó nuevamente iniciado al finalizar. Se conserva la cátedra técnica y el historial del
pedido; la instancia y su disco ya no existen.

La revisión posterior detectó que el pedido conservaba su aprobación histórica Activo
y podía mostrarse como un servicio operativo pese a la baja. La respuesta de Pedidos ahora
incluye `servicio_dado_de_baja`, calculado desde el servicio asociado. Listado y detalle
muestran **Servicio dado de baja**, conservando estados e historial originales y sin
anunciar disponibilidad ni ofrecer reintento del recurso eliminado. Se verificó esta
proyección también con el pedido 39 real, sin modificar sus registros históricos.

Las pruebas focalizadas de operaciones y recuperación (47 backend) y de acceso/interfaz
(21 antes de la regresión nueva) pasaron. Tras la corrección se comprobaron nuevamente
las 9 pruebas de baja y las 7 de interfaz de recuperación, incluida la nueva regresión.
Los 10 recorridos Playwright de operaciones y acciones quedaron comprobados; dos
pruebas que todavía esperaban confirmaciones nativas del navegador se actualizaron
para usar los diálogos vigentes de NAP. La compilación del frontend también pasó.

Alcance de esta evidencia: laboratorio de un nodo, API PVE real y servicios de dominio
de NAP. Se comprobó retención de la identidad de disco; no se escribió un archivo dentro
del guest ni se ensayó el login de consola de una persona de la universidad. Las pruebas
de contenido persistente, consola individual, acceso desde otros equipos y escenarios
multinodo institucionales se mantienen en la guía de aceptación, sin darlos por realizados.
