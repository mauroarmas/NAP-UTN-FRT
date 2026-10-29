# MariaDB PaaS: validación real del laboratorio

Validación: 28–29/10/2026. Proxmox local `172.16.36.100`, PVE 9.2.2,
kernel `7.0.2-6-pve`, arquitectura amd64. No acredita el clúster universitario.

## Combinación comprobada

- LXC Ubuntu 24.04 no privilegiado, AppArmor/seccomp activos, Docker anidado.
- Medium: 2 vCPU, 1024 MB RAM, 8 GB de disco. Small no fue validado.
- Imagen oficial `mariadb:11.4`, fijada al manifiesto
  `sha256:d9fc02976678d4236145299c40dc267051681b33489c994f0ec4a097ce4a9521`.
- Perfil `docker-ubuntu24:3`, SHA-256
  `0456c50bdb5e1e89d3ef44b6a26faef676a0fea49048f1abd70f0add850aaeeb`.
- Paquete de política:
  `4ebb0a71e161fd3d20c89a4c29ec60c1e735ac1cfe3cc0d7dcf732e133c18ac0`.
- Compuerta MariaDB: `e3df5339-0ec9-4105-97e6-1da990ec13c8`.
- Compuerta web whoami: respuesta HTTPS y perfil exacto comprobados; registro
  privado `web-evidence.json`.

El perfil está habilitado y coincide en nodo y portal. Las revisiones 1 y 2 se
conservan bloqueadas como históricas. El repositorio no habilita perfiles por sí
solo: la evidencia corresponde a esta instalación y a estos artefactos.

## Comprobaciones reales

El worker terminó confirmado y el cliente externo realizó `SELECT 1` verificando
la CA y la identidad TLS del servidor. Se rechazaron contraseña incorrecta,
CA no confiable, conexión sin TLS y root remoto. El usuario de la cátedra no pudo
leer `mysql.user`. Se escribió una fila y se recuperó después de apagar/iniciar y
reiniciar el LXC, con el mismo volumen y credenciales.

La receta ejecuta MariaDB como mysql, con todas las capacidades eliminadas salvo
la capacidad de puertos bajos compartida por el motor, y monta sus certificados
sólo para lectura. El almacenamiento es un volumen propio de la instancia.
El worker comprueba el aislamiento del LXC y las reglas de puente instaladas.
Las conexiones de prueba al nodo de gestión y a una dirección de otro servicio
no se establecieron; también se rechazó una conexión entrante desde el nodo.
Esto no equivale a una prueba con dos cátedras activas ni a una aceptación multinodo.

Whoami volvió a responder por HTTPS con verificación del certificado usando el
mismo paquete actualizado. Ambas compuertas se eliminaron, confirmando ausencia
de contenedores y discos. Su baja usó la misma limpieza de reglas que el portal;
el VMID auxiliar se reutilizó para la siguiente compuerta sin heredar reglas.

## Recorrido completo desde NAP

Pedido **41**, servicio **23**, cátedra técnica de verificación,
VMID **101**. Se usaron solicitud, evaluación, admisión y worker normales,
con las mismas reglas de autorización y configuración que los endpoints del portal.
No fue una automatización de clics ni una prueba de login de una persona docente.

1. Actualizar la oferta MariaDB y solicitar/aprobar el pedido PaaS.
2. Crear el LXC y desplegar la imagen, generando los secretos por pedido.
3. Ingerir y confirmar la consola; verificar una consulta TLS desde el portal
   antes de entregar acceso. Revelar sólo usuario/base de la cátedra y su clave,
   con CA pública; no entregar root.
4. Crear una tabla SQL y escribir una fila desde los datos de acceso entregados.
5. Detener: comprobar que el revelado de credenciales queda bloqueado.
6. Iniciar y reiniciar: recuperar la misma fila. La base necesitó un tiempo de
   arranque después de que Proxmox informó running; se esperó una consulta
   autenticada exitosa, sin reinstalar ni regenerar contraseñas.
7. Dar de baja: confirmar ausencia física, disco eliminado, reserva de red
   liberada, recursos retenidos en cero y reglas propias retiradas del nodo.

La oferta **MariaDB** quedó disponible para nuevos pedidos. Las instancias de esta
prueba se eliminaron; al cierre no había operaciones abiertas. API, gateway y
worker quedaron iniciados con los cambios. El pedido anterior fallido #40 y su
servicio #22 se conservaron como historia de diagnóstico, con su instancia eliminada.

## Correcciones que exigió la integración

- El portal conservaba otra CA: se agregó la CA pública del motor al conjunto
  de confianza y se conservó la anterior para Draw.io. No se deshabilitó TLS.
- Una regla histórica de un VMID reutilizado bloqueaba el despliegue. La nueva
  baja OCI usa una acción cerrada cleanup: exige ausencia del VMID en el clúster,
  identidad privada y recibo exacto de las reglas. Rechaza reglas ajenas o
  modificadas; un fallo conserva la reserva hasta reconciliar. La operación es
  idempotente ante pérdida de respuesta.
- La baja confirmada no llamaba a la liberación de red. Ahora lo hace en la
  misma transacción que retira la identidad y libera capacidad. Se repararon
  tres reservas históricas sólo después de observar ausencia y limpiar sus reglas.
- La actualización de perfil de MariaDB se ofrece mediante el botón existente
  Actualizar aplicación, conservando las configuraciones y decisiones anteriores.

Durante la ejecución, el worker normal envió un aviso automático de vencimiento
para el ensayo anterior #22. Se conserva su registro; no se ocultó ni se eliminó
el aviso enviado. El recorrido final #23 no generó correos de ensayo.

## Pruebas automatizadas y límites

- Motor OCI: **179 pasan, 3 omitidas** (las omitidas requieren su entorno de integración).
- MariaDB y catálogo: **22 pasan**.
- Ciclo de vida, baja y reservas de red: **27 pasan**.
- Recuperación e IaaS: **14 pasan**.
- Interfaz de alta, acceso y biblioteca: **15 pasan**; build Vite correcto.
- `git diff --check` correcto.

Estos resultados automatizados complementan las pruebas reales anteriores; no
sustituyen su evidencia. No se probó carga de un curso, host Proxmox reiniciado,
HA, migración en vivo, varios nodos ni la infraestructura universitaria.
No se implementaron backups SQL, builds de imágenes ni stacks libres.

Uso cotidiano: [MariaDB para prácticas](../../mariadb-paas.md).
