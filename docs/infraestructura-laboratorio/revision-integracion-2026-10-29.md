# Integración del laboratorio del compañero — 29/10/2026

## Integración y alcance de la revisión

Se incorporó `2fc95cb` mediante fast-forward en
`011-desplegar-servicios-universitarios`, desde `78af40e`. Son doce scripts shell,
una variante separada del gate y sus pruebas: catorce archivos agregados. No hubo
solapamientos ni conflictos. Se respaldaron fuera del repositorio los 99 archivos
con modificaciones locales y se verificó su contenido mediante SHA-256 después
de integrar. Los catorce archivos importados conservan el contenido del commit.

Esta revisión no ejecutó los scripts contra los nodos, no cambió configuraciones
privadas y no modificó el motor. La evidencia del laboratorio del compañero es
la comunicada por su agente: no se repitió aquí su despliegue ni se accedió a sus
servidores. El README anterior describe el estado histórico del 27/10/2026.

El commit `2fc95cb` no contiene las mejoras locales de MariaDB, acceso y limpieza.
Esas mejoras se consolidan en un commit posterior de esta misma rama; el compañero
debe actualizar al último commit publicado, no quedarse en `2fc95cb`. El respaldo de esta integración está bajo
`~/.local/share/nap011/integracion-companero/20261029-010054/`.

## Dos instalaciones distintas

| Instalación | Motor/evidencia | Alcance |
|---|---|---|
| Compañero: VirtualBox, `frt`/`pve91`, TrueNAS por NFS | Informe sobre el paquete `73e804b6…`, basado en `78af40e`; gate en `pve91` y nginx-unprivileged desde el portal | La definición habilitada incluye sólo `pve91`. Tener dos nodos no acredita despliegues en ambos ni migración/HA. |
| Mauro: Proxmox local `172.16.36.100` | Perfil `docker-ubuntu24:3`, paquete `4ebb0a71e161fd3d20c89a4c29ec60c1e735ac1cfe3cc0d7dcf732e133c18ac0` | MariaDB y whoami comprobados; evidencia en [MariaDB PaaS](../evidencia/011/mariadb-paas.md). |

Es esperable que cambie el hash del perfil al cambiar nodos, identidad de clúster
u otros campos de su definición, aunque coincidan base y plataforma. Actualmente
también cambió el paquete: los dos laboratorios no están en la misma revisión del
motor. No copiar hashes ni perfiles habilitados entre ellos. Los números de
pedido/servicio pertenecen a cada base: el servicio #23 informado por el compañero
no es el servicio #23 de nuestra prueba local.

## Contraste de los nueve hallazgos

| Nº | Estado observado en nuestro código actual | Decisión / siguiente trabajo |
|---|---|---|
| 1. Runner inválido deja aprobar | **Resuelto el 02/11/2026** (ver nota al pie). Antes: **vigente.** `verify_node_profile` retorna ante `RunnerError`; también omite la consulta si falta la entrada del nodo. | Prioridad alta: distinguir pruebas sin transporte de una instalación real y rechazar una aprobación/despliegue que no pudo comprobar el runner. Probar permisos inválidos de known_hosts sin enviar trabajos ni reservar capacidad. |
| 2. nginx oficial y capacidades | El contrato genérico sólo agrega NET_BIND_SERVICE a cap-drop=ALL. La biblioteca todavía no detecta esta incompatibilidad. El fallo de nginx y el éxito de nginxinc/nginx-unprivileged:8080 son resultados **informados por el compañero**, no una reproducción nueva aquí. | Conservar las restricciones generales. Tratar nginx-unprivileged como el caso que validaron y mejorar la explicación de compatibilidad; no afirmar que todas las imágenes de nginx o todos sus tags funcionan. |
| 3. Reglas huérfanas al dar de baja | **Resuelto localmente.** La baja OCI llama a cleanup antes de liberar identidad/capacidad. El nodo exige VMID ausente, identidad privada, recibo y reglas exactas; la repetición es segura. También se corrigió la liberación de dirección. | Mantenerlo en el motor. El compañero todavía necesita recibir esos cambios y comprobar la baja/reutilización en su laboratorio. No sustituirlo por borrado heurístico por hostname. |
| 4. Nodos offline impiden confirmar ausencia | **Vigente e intencionalmente conservador.** `observar` exige todos los nodos online, disponibilidad global del VMID y ausencia de volúmenes. | Conservar reservas y reconciliar cuando se recupere visibilidad. Una mejora para bajas con nodos offline requiere comprobar fencing, pertenencia y almacenamiento; no basta ignorar el nodo. Quitar miembros del clúster no es una solución automática del portal. |
| 5. Reintento Docker y acciones deshabilitadas | **Parcial.** El reintento crea reparar y conserva contexto del intento anterior; el ejecutor aún conduce ese caso al bootstrap histórico. La UI actual, en cambio, usa acciones_habilitadas: permite la baja administrativa con identidad incierta si no existe otra operación abierta. | Prioridad alta para reparación OCI: nuevo intento separado, secretos estables, identidad y estado previo reconciliados; nunca recreación/reinstalación ciega. Conservar los bloqueos cuando haya una operación abierta. |
| 6. CA del portal / bucle de comprobación | **Resuelto el 02/11/2026** (ver nota 6 y 7). Antes: la confianza en la CA **se configuró y comprobó localmente**; se conservó la CA anterior para Draw.io. Está documentada en la [guía de MariaDB](../mariadb-paas.md). La falta de CA aún puede terminar en un diagnóstico genérico durante verificación. | Validar esa configuración antes y dar un diagnóstico claro. En su portal deben confiar en la CA pública emisora de cada nodo que autoricen; nunca copiar ca.key al portal. |
| 7. Excepciones sin detalle | **Resuelto el 02/11/2026** (ver nota 6 y 7). Antes: **vigente.** Los bloques generales del worker usan logger.error sin traza. | Mejorar diagnóstico interno con tipo y ubicación de la excepción. Revisar redacción antes de habilitar exc_info=True global: el mensaje de una excepción puede contener valores privados. La consola del usuario debe seguir depurada. |
| 8. Mínimo de dos vCPU | **Documentado y conservado.** El perfil actual sólo valida Medium: 2 vCPU, 1024 MB RAM, 8 GB disco. | Respetar capacidad por nodo y los recursos efectivos de la VM que aloja PVE. No rebajar el mínimo ni considerar Small validado por este informe. |
| 9. Creación de CA del nodo | Su commit aporta `crear-ca-nodo.sh`: genera la clave en el nodo, se niega a sobrescribir PKI y comprueba InstanceTLS.from_node. Nuestra CA ya estaba creada y fue comprobada en el laboratorio. | Aprovecharlo como herramienta de ese laboratorio. Completar además la confianza pública del portal; crear una CA no configura automáticamente el acceso de los clientes. No ejecutar sobre nuestra PKI existente. |

No se implementaron cambios de comportamiento como parte de esta integración.
La prioridad de la siguiente corrección es 1 y 5, seguida del diagnóstico 6/7.
La política de ausencia en un clúster degradado se mantiene hasta tener evidencia
suficiente para cambiarla de forma segura.

## Respuestas a las preguntas del compañero

**¿Hace falta repetir exactamente con campus-demo?** No tiene que ser esa imagen
concreta. Whoami y nginx-unprivileged aportan evidencia útil del arranque y acceso
web en ese entorno. Para acreditar persistencia hay que escribir un dato, detener e
iniciar o reiniciar y recuperar el mismo contenido desde el volumen. Los scripts
incorporados sólo declaran `/data`: no contienen esa escritura/lectura posterior.
Si se hizo manualmente, documentar los pasos y el resultado. El canal de secretos
se declara y utiliza al lanzar el job, pero no se demuestra que la aplicación lo
use correctamente. Pull privado y uso funcional de secretos tampoco quedan
acreditados por esas dos corridas públicas. Campus-demo u otra app de prueba que
cubra esos casos completa la evidencia, sin convertir su nombre en requisito.

**¿Limpieza en el motor o paso operativo?** En el motor, y ya está implementada y
probada en nuestra copia local. El paso operativo queda para recuperar residuos
históricos, usando comprobaciones de identidad/ausencia y recibos; no para el
recorrido habitual del administrador.

## Precauciones concretas de los scripts importados

- `actualizar-nodos-011.sh` fija el digest antiguo `73e804b6…`, exige checkout limpio
  y empaqueta HEAD. Esa protección impide usarlo sobre nuestras mejoras aún sin
  commit. No quitar la protección ni cambiar sólo la constante para habilitar una
  combinación que no se comprobó.
- `habilitar-perfil-pve91.sh` comprueba cleaned y el hash de definición, pero no
  consulta que el job haya terminado confirmado ni registra una prueba de datos
  persistentes. Limpiar un gate fallido también deja cleaned. Esas condiciones
  por sí solas no autorizan a acreditar las cinco comprobaciones del perfil.
- `limpiar-tablas-huerfanas-pve91.sh` decide por prefijo de hostname. No verifica
  nonce, recibo ni hash de las reglas. Un invitado renombrado o el propio gate
  (`nap011-final-…`) puede no coincidir con ese prefijo. No ejecutarlo como limpieza
  general sobre instancias actuales.
- `diagnosticar-app-pve91.sh` crea otro contenedor, puede descargar imágenes,
  cambia el driver de logs y usa puerto 18081. No es sólo lectura ni reproduce
  todos los datos/volúmenes/secretos de la app original. El diagnóstico de start
  usa 18080, que puede estar ocupado. Reservarlos a invitados descartables.
- `quitar-nodos-offline.sh` ejecuta pvecm delnode con --aplicar. Es una intervención
  de infraestructura independiente, no una reparación automática de NAP. No se
  ejecutó ni se cambió el quórum de ningún clúster durante esta integración.

## Verificación de esta integración

- Fast-forward a `2fc95cb`; 99 archivos locales preservados byte a byte.
- Los catorce archivos del commit importado coinciden byte a byte con Git.
- Gates original y variante: **13 pruebas pasan**, sin efectos Proxmox reales.
- Sintaxis de los **16 scripts shell** presentes y parseo del gate Python: correctos.
- Digest del motor sin cambios: `4ebb0a71e161fd3d20c89a4c29ec60c1e735ac1cfe3cc0d7dcf732e133c18ac0`.
- Consulta real de capacidades al runner local: perfil 3 habilitado.
- Consulta de catálogo: MariaDB sigue disponible. API local: health OK.

Las comprobaciones locales de salud son de lectura y no sustituyen las pruebas
de despliegue del compañero ni las pruebas de MariaDB ya documentadas.

## Nota 02/11/2026 — hallazgo 1 resuelto

`verify_node_profile` ya no omite la consulta cuando hay runners configurados: un nodo sin entrada en
`runner_nodes` o un transporte inválido (por ejemplo `known_hosts` con escritura de grupo u otros) rechaza la
evaluación/aprobación con 409 `perfil_aplicacion_no_disponible`, sin abrir SSH, enviar trabajos ni reservar
capacidad. Sólo se omite cuando no hay **ningún** transporte configurado (pruebas y desarrollo con dobles).
Límite: si en una instalación real se olvida configurar `RUNNER_NODES` por completo, la comprobación sigue
omitiéndose; cerrarlo del todo cambiaría el comportamiento de muchas pruebas. Cubierto por
`backend/tests/test_verificacion_runner_011.py` (automatizado; no es una validación Proxmox real).
Suite completa del backend tras el cambio: 1108 pasan, 136 omitidas (las de PostgreSQL), 0 fallos.

## Nota 02/11/2026 — hallazgos 6 y 7 resueltos

**6. CA del portal.** Nuevo `backend/app/services/ca_portal_service.py`: distingue CA no configurada,
ilegible e inválida (también rechaza una clave privada puesta por error). Con runners configurados,
`verify_node_profile` rechaza evaluar/aprobar con 409 (`ca_portal_no_configurada`, `ca_portal_ilegible`,
`ca_portal_invalida`) antes de abrir SSH o reservar capacidad. Si la CA falla después, la verificación final
queda con ese código y un texto fijo en la operación, en lugar del genérico `consola_no_confirmada`.
Con un doble de la comprobación (pruebas) no se evalúa.

**7. Excepciones.** Nuevo `backend/app/utils/diagnostico.py`: registra tipos (con causas) y archivo:línea:función;
**nunca** el mensaje, argumentos ni variables. Se usa en los tres manejadores generales del worker, en
`infraestructura_io.ejecutar` (que descartaba la causa con `from None`) y en las comprobaciones web y SQL.
No se activó `exc_info` global. La consola del usuario no cambia.

Pruebas: `backend/tests/test_diagnostico_ca_011.py` (automatizado; no es validación Proxmox real).
Suite completa del backend: 1120 pasan, 136 omitidas (PostgreSQL), 0 fallos.
