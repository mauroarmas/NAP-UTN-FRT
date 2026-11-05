> Estado actualizado al 25/10/2026: el texto siguiente conserva el registro inicial de preparación. Después se agregaron ensayos locales declarados en linux-staging.json, postgresql-staging.json, bookstack-staging.json y gate-revocacion-consola-t101.json; T101 figura marcada en tasks.md. Esos JSON no habilitan por existencia el gate ni acreditan el clúster universitario. La configuración y evidencia aplicables a la instalación receptora se preparan según [conexion-infraestructura.md](../../conexion-infraestructura.md); T102/T119/T131/T133 siguen pendientes. Ver [convergencia.md](convergencia.md).

# Preparación institucional — T101/T102 pendientes

Estado actualizado al 21 de octubre de 2026. Implementación activa. Las imágenes Linux, PostgreSQL y BookStack están construidas/saneadas y copiadas a la VM; todavía no hay definiciones publicadas ni aceptación de entrega. Las notas anteriores de pausa o de imágenes sin construir se reemplazan por este estado.

| Elemento | Observado |
|---|---|
| PVE | 9.2.2, nodo `proxmox`, IP `172.16.36.100` |
| Imágenes y bundles | Seis archivos copiados con hashes verificados por el instalador root; tres imágenes reconocidas por API |
| Construcción | Snapshot separado `20ba2a308ae6d79b781c35d9800f1bb51f109638`; hashes en [imagenes-construidas.json](imagenes-construidas.json) |
| SSH runner | Cuenta dedicada, hostkey fijada, forced-command/sudo; protocolo real comprobado |
| TLS API | Certificado renovado para la IP actual; cliente de ensayo verifica CA recibida por SSH fijado |
| API staging | Cuenta/token separados `nap009lab@pve!ensayos`, vencimiento a 30 días; lecturas y permisos efectivos contrastados por HTTPS |
| Alcance de escritura | Sólo invitados del pool `nap009-staging`, espacio en `local-lvm` y uso de `vmbr0`; sin VM.Console ni administración del sistema/permisos |
| Invitados preexistentes | 101 y 103 detenidos, sin modificar |
| Registro del runner | Linux de staging registrado por el usuario con recibo root; PostgreSQL/BookStack todavía pendientes |
| Ensayos Linux | Se crearon 100/102; 100 arrancó sin IPv4 y 102 sigue detenido. Flujo detenido antes de bootstrap; diagnóstico root de networkd pendiente. [Estado](linux-staging.json) |
| Backend operativo | Configuración previa sin modificar; las comprobaciones usan un cliente de ensayo separado |
| Catálogo de laboratorio | Tres definiciones borrador, sin publicación; base independiente 55433 en revisión `009_10` |

El acceso API se recuperó después de dos intentos fallidos. El tercero confirmó éxito y conservó cuenta, roles y pool; sustituyó el token huérfano sin permisos y completó las ACL. La [verificación real](api-ensayo-verificacion.json) contrastó once rutas de permisos, lectura de nodos/storage/imágenes y el pool vacío antes de crear los ensayos. No se intentó escribir en 101/103 para comprobar una denegación: se contrastaron sus permisos efectivos. Esto no acredita una identidad docente ni revocación de consolas.

La receta Linux usa el hash del **manifiesto borrador** para staging y los artefactos exactos del build. [Registro preparado](registro-linux-preparado.json), [recibo root](registro-linux-recibo.json). No equivale al manifiesto final con evidencia ni habilita una oferta del portal. Las marcas de cada invitado conservan cluster/resource UUID, nonce hash, pool y hashes; el diario privado se persiste antes de cada POST/RPC. Un resultado incierto detiene el ensayo sin recrear ni liberar recursos a ciegas.

## Pendiente

- Completar dos ensayos Linux, login/sudo real y aislamiento/revocación de consola nativa antes de habilitar su entrega. El gate de consola permanece cerrado.
- Preparar registro, direcciones observadas, endpoints y TLS por instancia de PostgreSQL/BookStack. No hay IPAM ni CA automática de producto.
- Ejecutar dos ensayos por aplicación, con secretos distintos, datos persistentes y aislamiento; BookStack con dos lectores, revocación independiente y archivos privados.
- Importar evidencia institucional válida, finalizar manifiestos y publicar sólo después de los ensayos completos. Configurar perfiles/worker con acceso específico a los pools de cátedra; el token actual es de staging.
- Dos despliegues por producto desde el flujo del portal y desde otra computadora. El usuario confirmó que las primeras pruebas son desde esta PC; la otra computadora sigue pendiente.
- Confirmar identidad PVE individual del docente y procedimiento real para revocar permisos heredados/sesiones/consolas, conservando sus otros pools legítimos.

No habilitar consola mediante un flag ni llamar aceptación a las pruebas locales. En el registro original, T101/T102 estaban sin marcar; el estado vigente se aclara al inicio de este documento. La infraestructura institucional de clúster/red y el destino externo de respaldos siguen en preparación; por ahora se trabaja con esta VM.


Pausa solicitada por el usuario el 21 de octubre: los cuatro LXC 100/101/102/103 quedaron detenidos, con datos conservados; sólo se detuvo el 100 propio. VMware registra un bloqueo explícito de promiscuo y el dispositivo vmnet8 no da acceso a mauro. No se cambiaron esos permisos ni opciones de VMware. La captura individual confirma networkd activo y eth0 sin IPv4. [Diagnóstico](linux-red-diagnostico.json), [pausa verificada](pausa-laboratorio.json). Al retomar se preparará la corrección mínima del permiso y se revalidará DHCP antes de bootstrap. La VM puede apagarse.
