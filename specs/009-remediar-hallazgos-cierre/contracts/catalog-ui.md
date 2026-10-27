# Contratos de catálogo, acceso y experiencia

Contrato implementado en la feature 009. Complementa [auth.md](auth.md), [operations.md](operations.md) y [guest-runner.md](guest-runner.md). Prefijo /api/v1; autenticación, CSRF/Origin, errores e idempotencia siguen esos contratos.

## Catálogo y definiciones

| Método/ruta | Permiso | Resultado y reglas |
|---|---|---|
| GET /definiciones | Operativo | Versiones publicadas aptas para nuevas solicitudes; filtra por modelo. Admin puede incluir borradores/retiradas. Sin secretos ni datos del clúster para cátedra. |
| GET /definiciones/{id} | Operativo según alcance | Cátedra recibe producto, versión, finalidad, recursos recomendados/mínimos y parámetros de solicitud. Admin recibe manifest técnico/evidencia. Una referencia ya aprobada sigue resolviéndose aunque esté retirada. |
| POST /definiciones | Admin | 201, registra borrador con codigo/version/producto/modelo; sin ejecutar preparación ni habilitar catálogo. UNIQUE(codigo,version). |
| PUT /definiciones/{id}/manifest | Admin, solo borrador | 200, adjunta manifiesto construido y evidencia que debe satisfacer service-definition.schema.json. La API no descarga scripts ni ejecuta una receta indicada por el solicitante. |
| POST /definiciones/{id}/validar | Admin | 200, registra validación solo tras verificar schema, digest, evidencia del builder y compatibilidad con inventario/recetas instaladas. Error 422 de contrato o 409 de estado/evidencia no vigente. No acepta un simple booleano de aprobación. |
| POST /definiciones/{id}/publicar | Admin | 200, solo validada, evidencia e imagen/runner/perfil disponibles. Habilita solicitudes nuevas. |
| POST /definiciones/{id}/retirar | Admin | 200, motivo obligatorio. No modifica pedidos aprobados ni servicios existentes. No borra artefactos mientras existan referencias. |
| GET/POST/PATCH/DELETE /templates[/id] | Lectura operativa / mutación admin | Mantiene rutas actuales y baja lógica; nuevos templates solo LXC con definición compatible. Recursos positivos y mínimos del producto; sin cuota por cátedra. |

Versiones publicadas/validadas son inmutables; una corrección crea versión nueva. Las transiciones son borrador → validada → publicada → retirada. Se puede retirar una validada sin ofrecerla. No hay DELETE físico de una versión referenciada. “Disponible para altas nuevas” se diferencia de “utilizable por una aprobación previa”.

El builder produce el artefacto `validacion_definicion` definido en [evidence.md](evidence.md). Administración lo importa mediante `POST /evidencias`; el portal conserva el JSON canónico inmutable y devuelve UUID y checksum. `validation.evidence_id` y `evidence_sha256` del manifiesto deben coincidir con ese registro y con código/versión/digests del artefacto. Las imágenes/recetas siguen en el repositorio controlado de infraestructura; el ID de evidencia no permite apuntar a una ruta/URL libre. Publicación requiere dos instancias de prueba y resultados de integridad, saneamiento, bootstrap idempotente, aislamiento, persistencia y acceso. Los ensayos previos de preparación se realizan por operador técnico en entorno aislado, antes de ofrecer el producto desde NAP; no necesitan habilitar una definición sin validar al público.

El schema v1 delimita tres productos y recetas de referencia. Incorporar otro producto exige agregar su receta, parámetros, probes y validación al registro técnico/esquema; no cambiar las rutas o reglas del flujo genérico de solicitar/evaluar/aprobar/desplegar. La API nunca convierte una cadena de software libre en una instalación arbitraria.

Pedidos nuevos/reenvíos validan compatibilidad y disponibilidad. Al aprobar se fija definición, versión, snapshot de recursos y parámetros; desplegar usa ese snapshot. Retirar después del acuerdo impide nuevas solicitudes, pero permite cumplir aprobaciones previas si el artefacto sigue disponible y no existe bloqueo técnico explícito. Un problema de seguridad que impida ejecutar una versión exige incidente y nueva decisión registrada; nunca sustituir silenciosamente por otra.

## Acceso de un servicio

GET /servicios/{id}/acceso — sesión operativa con permiso actual sobre la cátedra, o administración. Retorna 200 con metadatos, sin contraseñas:

~~~json
{
  "servicio_id": 9,
  "modelo_servicio": "saas",
  "producto": "bookstack",
  "disponibilidad": "utilizable",
  "verificado_at": "2026-10-18T15:00:00Z",
  "metodo": "https",
  "direccion": "https://libros-catedra.example.edu",
  "puerto": 443,
  "puede_revelar_credenciales": true,
  "instrucciones": "Ingresá con tu cuenta docente. Creá las cuentas de lectura dentro de esta aplicación."
}
~~~

El dominio anterior es ilustrativo; no es dirección preconfigurada ni evidencia de conectividad. Si no se confirmó acceso, disponibilidad no_verificada/preparando/error y dirección solo observada cuando exista, con motivo y siguiente paso. No anunciar enlace ficticio. Al vencer o detener, mostrar datos conservados y razón de falta de disponibilidad, no prometer uso inmediato.

POST /servicios/{id}/acceso/revelar — mismos permisos, CSRF y Origin. 200 con credenciales tipadas y auditoría sin valores. Respuestas no-store, sin cookies de aplicación compartidas, secretos en URL ni inclusión en listados/correos. Repetir revelación no cambia contraseñas ni inicia infraestructura. 409 acceso_no_preparado si aún no existe acceso inicial válido. Tras bootstrap/health local y antes de verificar red, solo administración puede revelar credenciales para ejecutar esa prueba, con estado_entrega=solo_validacion; no se anuncian como entrega utilizable. La cátedra accede al revelado ordinario después de verificar red. 403 antes de descifrar si falta permiso.

| Producto | Revelado permitido al responsable | Valores internos no revelados por este endpoint |
|---|---|---|
| Linux LXC | Usuario y contraseña del invitado propio, según receta; instrucciones de consola. | Token PVE, clave runner, secretos de otras instancias. |
| PostgreSQL | Host, puerto, base, usuario y contraseña de esa instancia. | Superusuario, claves del portal e identidad de infraestructura. |
| BookStack | Dirección y usuario/contraseña inicial docente de esa aplicación. | APP_KEY, contraseña de MariaDB, clave runner. |

Proxmox console conserva la excepción constitucional: enlace al destino de consola concreto solo tras pertenencia verificada y ACL/pool de todas las cátedras propias. No entregar cuentas con visibilidad de clúster. Las credenciales dentro de Linux son distintas de la identidad Proxmox para abrir la consola.

Las credenciales iniciales BookStack pueden quedar desactualizadas si el docente las cambia en la aplicación; se indica “acceso inicial entregado”, sin afirmar sincronización continua de contraseñas. La monitorización no depende de que esa contraseña docente permanezca igual. NAP no resetea lectores ni sincroniza usuarios.

## Estado visible y sesión

- Inicio SPA: estado de carga de sesión hasta GET /auth/me, sin confiar en perfil local; eliminar token/user antiguos de Web Storage y tolerar contenido inválido. 401 vuelve al ingreso; 403 por habilitación pendiente abre el paso correspondiente.
- Login: contraseña → MFA solo cuando está activo → cambio inicial si pendiente → portal. Configurar 2FA es una elección explícita desde seguridad de cuenta; iniciar/cancelar no bloquea el ingreso por contraseña.
- Recuperación: pantalla restringida, vencimiento visible, nuevo factor y códigos al confirmar. No renderizar datos operativos detrás del modal de habilitación.
- Peticiones usan credentials de cookie y CSRF en memoria; rotación obtiene otro CSRF. Cerrar sesión revoca en servidor. Expiración no pierde formularios no sensibles mientras se informa que debe autenticarse.

## Formularios y navegación

| Recorrido | Comportamiento exigido |
|---|---|
| Nueva solicitud | Reinicia al abrir, cátedra/modelo/template compatibles; cambiar modelo elimina opciones incompatibles. Sin VMID/nodo/template PVE para docente. |
| Responder aclaración | Administración o titular actual del pedido propio, sólo en `requiere_ajuste`. Recupera datos editables sin hardware; modalidad académica usa año/período configurados y personalizada exige rango. Reenvía a revisión y avisa a administración. |
| Aprobación | Muestra asignación/destino/fechas efectivos; al editar invalida evaluación. Sobreasignación muestra cifras y exige motivo; 409 conserva formulario y solicita reevaluación. |
| Futuro/receso | Explica desde cuándo puede desplegar/reactivar y cuándo vence la reserva. Fecha habilitada no significa ejecución automática. Receso informa pausa/datos conservados/capacidad al reactivar. |
| Acción de servicio | 202 muestra progreso y operación; no toast de éxito final ni cambio a running hasta confirmar. Al recargar conserva seguimiento desde servidor. |
| Catálogo/filtros | Modelo IaaS/PaaS/SaaS desde snapshot, independiente de lxc. Plantillas retiradas siguen legibles en historial. |
| Copiar datos | Éxito solo si Clipboard API confirma; error ofrece seleccionar/copiar manualmente sin ocultar el acceso. No copiar secretos por defecto. |

Cancelar sólo aparece para administración. La cátedra ve «Responder aclaración» únicamente en un pedido propio devuelto; puede corregir la solicitud sin hardware ni decisiones de aprobación. «Pedir aclaración» registra el aviso de portal y encola correo según preferencias. Una reasignación/retiro que requiera retirar consola se muestra pendiente o fallida según [console-access.md](console-access.md); no hay toast de cambio completado ni acceso del nuevo titular antes de confirmar. El formulario admin de evidencias importa un JSON acotado, muestra tipo/instancia/origen/resultados y conserva el UUID devuelto; no pide una URL libre. Nunca muestra cookies, nonce sin hash ni contraseñas.

Operación en curso impide doble confirmación del mismo recurso; se permite consultar/operar otros recursos independientes. Polling inicial de operación cada dos segundos con pausa al ocultar la pestaña y backoff ante fallo; al volver se consulta resultado. Un estado incierto ofrece seguimiento/administración, no un botón que envíe create de nuevo.

## Estados de datos y accesibilidad

Todo listado/consulta distingue carga inicial, vacío confirmado, error sin datos y datos anteriores con fecha/aviso. Fallar una petición de Promise.allSettled no reemplaza sus datos por arreglo vacío. Mostrar reintento por bloque; error parcial de métricas no borra servicios confirmados. Peticiones canceladas no sobrescriben un formulario/recurso diferente.

Dialog compartido debe tener nombre accesible, semántica modal, foco inicial adecuado, ciclo Tab/Shift+Tab contenido, Escape cuando cancelar sea válido, retorno de foco y fondo inerte. Errores de campos relacionados con etiquetas y aviso de resultado mediante región accesible; iconos accionables tienen nombre. La habilitación obligatoria requiere una pantalla propia o modal sin navegación al fondo, no un overlay con portal operativo detrás.

Carga diferida de rutas y gráficas; consultas acotadas y deduplicación de polling. Las gráficas tienen alternativa textual con estado, consumo y período; no exigir interpretar CPU de host al docente.

## Configuración e interfaces operativas

Configuración nueva prevista: APP_FRONTEND_URL/origins, proxies confiables, keyring de cifrado, clave CSRF distinta de JWT, cluster_id, perfiles de nodo/storage/red, rutas runner/known_hosts y habilitación de scheduler. API con scheduler desactivado; worker lo ejecuta con locks compartidos.

Modo operativo exige HTTPS/origen real, SECRET_KEY no conocida, keyring/CSRF presentes, verificación TLS PVE con CA confiable, token de privilegios mínimos, acceso DB protegido y configuración SMTP explícita. Fallar preflight muestra qué falta sin volcar secretos. No usar root@pam/token de demostración por defecto ni seeds al reiniciar. Desarrollo conserva servicios de prueba separados.

Arranque: migración como paso de release controlado, API/worker sin recrear cuentas. Alta inicial mediante CLI interactiva única definida en auth.md, sin actualizar una cuenta existente. Los backups externos no se agregan a pantallas ni endpoints del portal.

Pruebas: estados de sesión/carga y evaluación con componentes; login opcional MFA, formulario y operación/recarga con Playwright; teclado completo y lector no editor en BookStack real. La validación con el responsable de una cátedra y el acceso desde red alumno requieren evidencia de aceptación, no se deducen de npm build.
