# Operación de respaldos y recuperación

## Estado y responsabilidades

El usuario confirmó el 2026-10-21 que el clúster y su red están en armado y que actualmente se trabaja con la VM. El destino externo está pendiente de acordar con el cliente. No hay una copia externa diaria configurada ni una restauración real aceptada. La documentación define el procedimiento que debe completar operación; no crea un módulo NAP de backup.

| Responsabilidad | Función | Estado institucional |
|---|---|---|
| Responsable del servicio | Acordar datos críticos, ventana de corte, RPO/RTO y aprobar recuperación | Persona por designar con el cliente |
| Operador de respaldos | Ejecutar copia consistente, transferir, comprobar integridad/retención y revisar fallos | Persona por designar |
| Custodio de recuperación | Proteger claves/recipientes de cifrado, controlar acceso y conservar instrucciones fuera del origen | Persona por designar; custodia independiente |
| Operador de restauración | Restaurar separado, revocar credenciales efímeras, reconciliar y registrar aceptación | Persona autorizada por designar |
| Responsable de cátedra | Pedir su servicio y validar datos/permisos del ensayo funcional | Un único responsable por cátedra; no asume administración de respaldos por ese motivo |

La copia diaria debe almacenarse cifrada fuera de la PC/VM origen. Completar antes de operar: identificador del destino y aislamiento físico/lógico, protocolo/cuenta dedicada, capacidad, conectividad, recipiente de cifrado, custodio, calendario de verificación y ventana autorizada. Guardar credenciales únicamente en el gestor/archivo privado de operación. Si hay disco externo, definir conexión, custodia y desconexión; si hay servidor/almacenamiento remoto, definir permisos, cuotas y protección contra borrado desde la cuenta origen.

Retener siete copias diarias y cuatro semanales. No borrar la última copia comprobada cuando falle la nueva transferencia, ni purgar antes de verificar integridad y disponibilidad de las claves. El registro de ejecución contiene fecha de corte, versión de aplicación/esquema/recetas, tamaños/hashes, destino lógico, operador, duración y resultado; no secretos. La programación externa debe alertar al operador si falta una copia o falla la verificación.

## Conjunto que se respalda

- Portal: dump lógico PostgreSQL en formato custom, roles/permisos necesarios, revisión Alembic, versión/imagen de aplicación y configuraciones privadas de runtime/release. El dump por sí solo no incluye todos los roles del clúster PostgreSQL; conservar su definición de forma protegida o reconstruirlos con el procedimiento de roles y permisos.
- Claves: keyring completo con todas las versiones utilizadas, identificadores activos, claves JWT/CSRF y configuración. Para recuperación reproducible, preservar también referencias de CA, huellas SSH y cuentas de infraestructura. No regenerar el keyring para abrir una copia: perdería MFA, nonces, credenciales de servicios y destinatarios cifrados.
- Catálogo: manifiestos/versiones, hashes, imágenes, bundles y evidencias; registros institucionales de red/runner y las relaciones UUID/clúster/pool. Los datos de servicio pertenecen al conjunto, además de su receta de reconstrucción.
- PostgreSQL PaaS: dump consistente de la base del curso y roles/permisos específicos. Usar pg_dump compatible con la versión del servidor; para el portal se usa PostgreSQL 16. Un archivo de imagen LXC no contiene necesariamente los datos del curso.
- BookStack: dump consistente de MariaDB, archivos subidos públicos/privados, imágenes y adjuntos, configuración de la aplicación y APP_KEY original. Preservar usuarios/roles/permisos, propietario y permisos de archivos. Proteger .env/APP_KEY dentro de la copia cifrada, sin incluirlos en informes.
- Inventario externo: identificadores del clúster/nodo/VMID/UUID, almacenamiento, volúmenes y puntos de montaje, DNS/endpoints/TLS, cuentas nativas y alcance concedido. Conservar referencias para reconciliar el corte sin adoptar por nombre ni recrear recursos que ya existen.

El dump, keyring y archivos de aplicación forman un conjunto de recuperación. Aplicar el mismo control de acceso/cifrado a configuraciones y material criptográfico; sus versiones deben corresponder al corte. La custodia debe permitir recuperar el conjunto aunque se pierda el host origen.

## Corte diario consistente

1. Identificar operador, ventana, servicios y referencia única del corte. Comprobar espacio, destino, herramientas compatibles y disponibilidad de claves. Registrar tiempo inicial UTC. Detener worker/outbox y bloquear nuevas escrituras del portal durante el corte coordinado; no interrumpir una operación de infraestructura sin registrar su estado/UPID.
2. Poner BookStack en mantenimiento y detener su scheduler/procesos que escriben o importan archivos. Impedir escrituras de usuarios durante todo el corte MariaDB/archivos. Obtener dump transaccional de tablas InnoDB con mariadb-dump y copiar los directorios de datos subidos/configuración/APP_KEY del mismo corte. Si existen tablas no transaccionales, acordar bloqueo/paro adicional; no atribuir consistencia transaccional a esos datos.
3. Obtener dumps PostgreSQL de portal y servicio PaaS con pg_dump, más la definición protegida de roles/permisos. Para un corte coordinado entre productos, mantener suspendidas sus escrituras hasta terminar todos los componentes. Usar archivos de credenciales protegidos; no poner contraseñas en argumentos ni guardar una URL privada en el historial de terminal.
4. Empaquetar dumps, archivos, inventario, versiones y claves dentro del conjunto privado. Registrar hashes y tamaños; cifrar el paquete con el recipiente acordado. Comprobar descifrado/integridad en un área temporal privada del operador sin publicar secretos.
5. Transferir al destino externo, verificar hashes/retención y registrar resultado. Sólo entonces aplicar la política siete diarias/cuatro semanales. Si falla la transferencia, conservar la copia previa e informar al responsable. Reanudar servicios según la ventana acordada y revisar estado de operaciones, correo y aplicaciones.

Una instantánea del hipervisor puede complementar el procedimiento si se comprueba su consistencia; no reemplaza la comprobación conjunta de base/archivos/APP_KEY/keyring ni la transferencia externa acordada. La programación pertenece a operación del clúster, no al scheduler del portal.

## Restauración separada

1. Elegir un corte y verificar recipiente, hashes y versiones. Registrar hora del último dato confirmado del corte y hora del incidente/ensayo. Restaurar en base, volúmenes y red separados; impedir acceso a SMTP/PVE reales y a los visitantes hasta reconciliar. No sobreescribir el origen ni arrancar el worker restaurado.
2. Restaurar roles/esquema/datos del portal y el keyring/configuración correspondientes. Verificar descifrado antes de mutar cuentas. Aplicar versiones compatibles de las migraciones sobre la copia. Un downgrade que borre historia no es el procedimiento de recuperación.
3. Ejecutar el [preparador de restauración](preparar-restauracion.md) antes de habilitar API/worker/outbox: configurar una referencia externa nueva, revocar sesiones/desafíos/códigos recuperados, preservar factores 2FA activos y cancelar bienvenidas/secretos temporales antiguos. Las cuentas que necesiten nueva entrega se resuelven mediante administración autorizada, sin recrear cuentas predeterminadas ni desactivar su MFA.
4. Reconciliar inventario real, identidades UUID/nonce/pool/clúster, operaciones/UPID, compromisos y acceso nativo. La ausencia o una consulta fallida no liberan capacidad. Mantener bloqueados los casos inciertos; no recrear contenedores por inferencia del VMID. Volver a habilitar trabajos sólo con referencia de prueba separada y revisión institucional.
5. Restaurar PostgreSQL PaaS y comprobar el dato del curso, autenticación y permisos. Restaurar MariaDB/archivos/configuración/APP_KEY de BookStack como conjunto y verificar un libro con imagen y adjunto, cuentas y permisos. Comprobar la denegación entre cuentas/cátedras ajenas, no sólo que abra la página inicial.
6. Probar el portal, MFA activo/opcional según la cuenta, nueva sesión, consulta/solicitud, operaciones, correo y acceso de servicios desde la red prevista. Registrar datos comparados y resultados sin contraseñas. Mantener el entorno de origen hasta decidir el retorno/puesta en servicio.

RPO observado: diferencia entre el último dato de negocio durable previo al incidente y el dato más reciente comprobado en la copia recuperada. RTO observado: desde el inicio del procedimiento hasta completar las comprobaciones acordadas y habilitar el acceso. Registrar tiempos observados, volumen y hardware; no presentar una meta como medición. Una frecuencia diaria permite planificar una ventana de pérdida de hasta el último corte diario exitoso; fallos de copia pueden ampliarla.

Se verificaron el control de restauración/revocación en [restauracion-control.md](evidencia/009/restauracion-control.md) y las migraciones mediante suites PostgreSQL aisladas. No se encuentra evidencia de un ensayo completo de pg_dump/pg_restore del portal+keyring ni del contenido de las aplicaciones; no se consideran recuperaciones aceptadas. T131 conserva la ejecución de la restauración completa y separada con comparación de datos/permisos y RTO/RPO. T133 conserva el recorrido desde otra computadora con ambos roles, SMTP y aplicaciones. El destino externo y sus custodios se completan con infraestructura; por ahora se trabaja con la VM.


## Referencias de operación

- [Manual de Administración y Operación](manual-administrador.md)
- [Manual de Usuario Docente](manual-docente.md)
- [Guía de Despliegue Docker](../DOCKER.md)
- [Preparador de Restauración](preparar-restauracion.md)
- [pg_dump PostgreSQL 16](https://www.postgresql.org/docs/16/app-pgdump.html), [pg_dumpall y roles](https://www.postgresql.org/docs/16/app-pg-dumpall.html), [respaldo BookStack](https://www.bookstackapp.com/docs/admin/backup-restore/) y [mariadb-dump](https://mariadb.com/kb/en/mariadb-dump/). Los scripts/recetas de servicio fijan versiones; confirmar las opciones de la herramienta de esa versión antes de ejecutar el corte.

## Datos de biblioteca (010)

Incluir en el respaldo las incorporaciones, revisiones técnicas, ensayos/operaciones/eventos, recursos e identidades, artefactos/réplicas, presupuesto/reservas builder y publicaciones. Conservar además los paquetes finales, registros dinámicos root, locks de inputs y el estado durable del builder (incluidos tombstones de cancelación fuera de `work`). Respaldar el keyring externamente: cifra también las credenciales de recursos de ensayo.

Preparar una restauración cerca ensayos del corte, incrementa generaciones y deja limpieza fallida para conciliación, sin liberar reservas ni reanudar builds automáticamente. Confirmar estado remoto de trabajos y tareas PVE antes de reintentar limpieza; no borrar sus registros para forzar reenvíos. La habilitación comprueba nuevas tablas e impide un corte con ensayos sin limpieza confirmada. Los artefactos/versiones históricos se conservan incluso si ya no se ofrecen a docentes.
