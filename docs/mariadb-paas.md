# MariaDB para prácticas (PaaS)

NAP ofrece una instancia MariaDB 11.4 por pedido aprobado. Usa el mismo motor
Docker dentro de un LXC Ubuntu 24.04 no privilegiado. No instala Docker en el
nodo Proxmox. No incorpora Compose, builds ni un segundo motor de despliegue.

## Recorrido cotidiano

1. Administración agrega `mariadb:11.4` desde Docker Hub o Imagen propia. La
   configuración de base de datos se completa automáticamente. Agregarla al
   catálogo no crea instancias ni reserva capacidad.
2. La cátedra solicita MariaDB con propósito y fechas. Administración aprueba y
   NAP reserva capacidad y despliega cuando corresponde.
3. NAP genera una base `catedra`, un usuario `docente` y una contraseña distinta
   para cada pedido. El usuario administra esa base; no tiene acceso a otras.
4. El despliegue comprueba aislamiento, arranque y una consulta `SELECT 1` con
   autenticación y TLS. El portal repite la consulta desde la red autorizada
   antes de mostrar el servicio disponible.
5. En **Servicios → Ver acceso → Revelar acceso inicial** se muestran dirección,
   puerto 3306, base, usuario, contraseña y descarga de la CA pública. El cliente
   debe usar TLS, esa CA y verificación de identidad del servidor. No se usa el
   acceso web de aplicaciones ni se entrega una consola de administración SQL.

Las credenciales se revelan sólo a quienes tienen acceso a la instancia,
cuando está iniciada y dentro de su vigencia. La revelación queda auditada;
no copia la contraseña automáticamente. La clave de administración de MariaDB
es distinta, queda restringida a localhost y no se entrega en la interfaz.
Si se cambia la contraseña dentro de MariaDB, el acceso inicial de NAP conserva
el valor original; usar la nueva contraseña en el cliente.

## Recursos y datos

- Perfil inicial **Medium: 2 vCPU, 1024 MB RAM y 8 GB de disco**. Small no está
  validado para este motor. Mantener apagadas las prácticas que no se estén usando.
- Después de iniciar o reiniciar, Proxmox puede mostrar la instancia encendida
  unos segundos antes de que MariaDB acepte conexiones.
- `/var/lib/mysql` se conserva en un volumen propio dentro del disco de la
  instancia. Detener, iniciar y reiniciar conservan los datos.
- Dar de baja destruye la instancia y sus datos. Exportar lo que deba conservarse
  antes de la baja. NAP no incorpora copias de seguridad de bases en este alcance.
- El acceso directo se limita a la red de clientes configurada. No publicar el
  puerto en Internet ni copiar direcciones o certificados del laboratorio a la universidad.

## Habilitación de infraestructura

La receta está cerrada: imagen oficial fijada por digest, usuario/base y puertos
fijos, secretos generados, TLS obligatorio y volumen persistente. No transforma
cualquier imagen MySQL o MariaDB en una oferta compatible. Las configuraciones
históricas de MariaDB con acceso HTTP deben reemplazarse por esta configuración.
Redis permanece fuera del alcance.

La configuración privada `mariadb_application_validation` vincula el digest de
la imagen con la referencia exacta del perfil Docker y comprobaciones reales de
aislamiento, TLS, autenticación, persistencia y recuperación. Vacía por defecto:
no habilita una instalación universitaria sin su propia prueba. Un cambio del
perfil o del digest requiere comprobar la nueva combinación antes de ofrecerla.
El portal debe confiar en la CA pública que firma las instancias (`application_gateway_ca_file`);
si conserva aplicaciones anteriores, usar un conjunto de CAs que incluya ambas.
Las claves de firma permanecen exclusivamente en infraestructura.
La evidencia local se conserva en [evidencia/011/mariadb-paas.md](evidencia/011/mariadb-paas.md).

La baja OCI retira también las reglas de red propias del nodo: el runner exige
que el VMID esté ausente en todo el clúster y que coincidan la identidad privada,
el recibo de instalación y las reglas actuales. Sólo después se libera la
reserva de red y capacidad. Si no puede comprobarse esa limpieza, el recurso
permanece pendiente de reconciliación; no se devuelve el identificador para otro
pedido. Las reglas ajenas o modificadas no se borran.
