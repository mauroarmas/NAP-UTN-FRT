# Conectar NAP al clúster universitario

Guía de cierre académico actualizada el 28/10/2026. El objetivo es gestionar los
recursos autorizados de las cátedras: conocer capacidad, crear instancias, consultar
su estado, iniciarlas, detenerlas, reiniciarlas y darlas de baja con historial.
Las aplicaciones adicionales no son un requisito para conectar el clúster.

El laboratorio local tiene un nodo y comprobaciones propias. La universidad necesita
sus direcciones, certificados, permisos y verificación real; sus datos todavía no
están confirmados. Las pruebas automatizadas multinodo no acreditan esa instalación.

## Información que entrega infraestructura

| Elemento | Datos que hay que comprobar una vez |
|---|---|
| Plataforma | Arquitectura compatible con las plantillas amd64 actuales, versión PVE, identidad del clúster y nombres de los nodos. |
| API | Dirección y puerto, CA pública verificada y cuenta/token dedicado con permisos para los recursos autorizados. |
| Capacidad | CPU y RAM utilizable por nodo, margen para Proxmox y otros servicios, y almacenamiento disponible. La estimación inicial de 8 GB totales debe confirmarse. |
| Storage | Qué almacenamientos son compartidos o locales; cuáles admiten contenedores (`rootdir`) y dónde están las plantillas (`vztmpl`). |
| Red Linux | Bridge/VLAN, DHCP o direcciones reservadas, gateway y alcance desde los equipos que usarán los servicios. |
| Acceso | Identidades individuales para la consola nativa, pools de las cátedras y permisos efectivos. |
| Portal | Equipo que ejecutará NAP, dirección HTTPS, certificado y ubicación privada de configuración, claves y respaldos. |

Un storage compartido aporta disco al clúster; la CPU y la RAM siguen perteneciendo
a cada nodo. NAP tiene en cuenta los recursos existentes y los compromisos pendientes
antes de admitir un despliegue. El catálogo no consume capacidad por sí mismo.

## Preparación del camino IaaS

1. Preparar la conexión HTTPS a PVE con CA verificada y permisos mínimos. Las credenciales
   quedan fuera del repositorio y se montan mediante el archivo privado de configuración.
2. Completar `infrastructure_profile`: identidad del clúster, nodos y storages autorizados,
   carácter compartido/local y márgenes de capacidad reales.
3. Descargar una plantilla estándar compatible de Ubuntu 24.04 o Debian 13 en el storage
   de plantillas configurado. Para el primer ensayo basta un sistema y un nodo.
4. Preparar la red Linux en `network_profiles` y seleccionar `iaas_network_profile_id`.
   NAP admite DHCP o la asignación estática preparada; no toma las direcciones del laboratorio
   como valores de la universidad. Si se usa storage compartido, comprobar su visibilidad
   y contenido desde cada nodo autorizado.
5. Abrir Inicio para comprobar nodos y almacenamiento, y Catálogo para actualizar las
   bases Linux. El saldo útil para un pedido se comprueba al evaluar su aprobación.

Los pools por cátedra se comprueban y se crean cuando corresponde durante el despliegue.
NAP no adopta recursos ajenos ni concede permisos nativos por el mero hecho de crear un pool.

El camino IaaS utiliza la API de PVE y las plantillas Linux. La instalación del motor
Docker/OCI y del preparador de aplicaciones corresponde a los servicios que lo necesiten;
no condiciona la primera demostración de creación y operación de un entorno Linux.

## Gate de consola por instalación

El acceso del portal y el acceso nativo a Proxmox son identidades distintas. Cada persona
que use la consola necesita su cuenta individual y los permisos institucionales sobre
los pools correspondientes. NAP no comparte el token de administración con el navegador.

`console_access_profile` registra la configuración y la comprobación institucional de
ese acceso. Las concesiones y revocaciones se validan por instalación, incluida la
terminación de sesiones anteriores. Los cambios de titularidad o rol invalidan las
comprobaciones que ya no correspondan. Los detalles técnicos están en
[acceso nativo y revocación](../specs/009-remediar-hallazgos-cierre/contracts/console-access.md)
y en los contratos de consola de la spec 009.

En Linux, Ver acceso permite recuperar las credenciales de la instancia una vez
completada la preparación. La consola nativa sigue requiriendo el acceso individual
válido a Proxmox; una contraseña del guest no sustituye esa autorización.

## Comprobaciones de conexión y aceptación

Antes de habilitar la instalación institucional, ejecutar desde su entorno configurado:

```bash
python -m scripts.preflight --datos --inventario
```

El informe debe indicar los requisitos pendientes sin imprimir secretos. La configuración
operativa y sus archivos privados se describen en [DOCKER.md](../DOCKER.md). No cambiar
el entorno de desarrollo del laboratorio a producción sólo para hacer pasar el informe.

Recorrido de aceptación:

1. Solicitar un Linux Small con fechas actuales, aprobarlo y desplegarlo. Comprobar el
   recurso en PVE, su nodo/storage, su propiedad y el estado que muestra NAP.
2. Consultar Ver acceso y probar la consola con la identidad individual autorizada.
3. Guardar un archivo de prueba, detener y volver a iniciar; comprobar su contenido.
   Reiniciar y repetir la comprobación. Detener conserva disco y libera CPU/RAM.
4. Dar de baja exclusivamente la instancia de prueba. Confirmar ausencia de contenedor
   y volúmenes antes de dar por liberados los recursos; conservar el historial.
5. Repetir con otra cátedra y comprobar que no puede operar ni revelar el acceso de la
   primera. Verificar el reparto entre nodos/storage cuando estén disponibles.
6. Comprobar falta de capacidad, consulta fallida, resultado incierto y recuperación
   sin crear una segunda instancia. Distinguir el último estado conocido del actual.
7. Medir una demostración de 2–3 instancias si hay saldo suficiente y documentar el
   límite observado, incluyendo el consumo del portal y del hipervisor.

La evidencia debe separar comprobaciones reales, pruebas con dobles y pendientes.
La lectura de inventario no acredita creación/baja; una instancia encendida no acredita
el funcionamiento de una aplicación. Ver [evidencia del ciclo local](evidencia/011/administracion-instancias.md).

## Aplicaciones y ampliaciones posteriores

El alcance actual conserva los servicios ya comprobados y las imágenes web propias
compatibles. Para instalar el motor OCI y preparar su red/TLS, seguir
[despliegue de aplicaciones](despliegue-aplicaciones.md) y el paquete de infraestructura
correspondiente. No configurar MariaDB, Memos ni BookStack para completar este cierre:
son ampliaciones futuras y requieren su propia comprobación.

Los registros antiguos y los mecanismos de recuperación de sus instancias conservan
su historial. Sus antiguos pasos de construcción y preparación no son el recorrido
habitual del catálogo actual.

## Laboratorio local de biblioteca

La preparación de la VM y el constructor de esta PC se documentan en
[laboratorio de biblioteca](laboratorio-biblioteca.md). Sus identidades, certificados y
acceso local pertenecen al laboratorio; no se trasladan como valores institucionales.
