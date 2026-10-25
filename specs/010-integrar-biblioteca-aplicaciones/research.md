# Investigación: biblioteca de aplicaciones reutilizables

Fecha: 2026-10-25. Base: [spec.md](spec.md), constitución 4.0.0 y árbol de trabajo actual de la rama 010. Se investigaron integración externa y código existente en paralelo. No se ejecutaron instaladores, construcciones ni operaciones PVE.

## 1. Descubrimiento y comando de Community Scripts

**Decisión:** adaptador de lectura del repositorio oficial `community-scripts/ProxmoxVE`, usando una revisión resuelta y los scripts `ct/*.sh` como identidad externa. Índice NAP de alias/categorías; `drawio`, `draw.io` y `diagramas` apuntan a `ct/drawio.sh`. El comando se deriva de ruta/revisión validadas y se muestra como procedencia. No se interpreta shell para obtener metadatos ni para instalar.

**Motivo:** la búsqueda sólo debe aportar el comando y los datos efectivamente disponibles. La antigua ruta `main/json/drawio.json` devolvió 404 durante esta investigación; no se presupone una API JSON del catálogo web. Listar rutas públicas es una interfaz verificable. Categorías y alias añadidos por NAP se identifican como tales; otros datos pueden ser desconocidos.

**Alternativas:** scraping de la web (frágil); antigua API JSON (no verificada); incorporar un marketplace completo (fuera del piloto).

**Fuentes:** [ficha oficial](https://community-scripts.org/scripts/drawio), [Git Trees API](https://docs.github.com/en/rest/git/trees?apiVersion=2022-11-28), [script del host](https://github.com/community-scripts/ProxmoxVE/blob/main/ct/drawio.sh). Revisión del repositorio observada: `e1ced742563b9916b1d76692899e6397a89bdbd3`; es evidencia de investigación, no versión obligatoria de una preparación futura. La implementación fijará y probará sus propios fixtures.

## 2. El comando descubierto no es un instalador de guest

**Decisión:** conservar el comando externo sin ejecutarlo desde NAP. Un adaptador cerrado de Draw.io traduce la preparación en construcción institucional y ensayos creados por servicios NAP. Otras fichas se pueden incorporar como borradores, pero no preparar/publicar sin adaptador.

**Motivo:** `ct/drawio.sh` carga el motor remoto y crea contenedores; ejecutarlo directamente eludiría reservas, VMID, propiedad y reconciliación del portal. El instalador de guest también depende de ese motor y descarga un WAR con referencia móvil. No se considera una receta estable ni autónoma.

**Alternativas:** ejecutar el comando en el nodo (rechazado); ejecutar el script de guest literalmente (dependencias implícitas); admitir shell libre (fuera de alcance).

**Fuentes:** [ct/drawio.sh](https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/drawio.sh), [drawio-install.sh](https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/install/drawio-install.sh).

## 3. Artefacto preparado y runtime

**Decisión:** ampliar `infra/services/build_image.py` con receta `drawio-tomcat11-ubuntu-24.04-v1`, bootstrap `drawio-v1` y producto `drawio`/SaaS. Mantener base Ubuntu 24.04 amd64, LXC sin privilegios y sin nesting. Instalar JRE 21, Tomcat 11 y WAR oficial Draw.io, junto con nginx para TLS y control de acceso por instancia. Resolver antes del build una versión exacta de cada componente, inventario completo de paquetes y hashes de descargas; persistir ese lock y requerir confirmación administrativa de sus entradas. No usar `latest` durante construcción, bootstrap ni despliegue.

**Motivo:** el builder existente ya produce rootfs `.tar.gz` saneado, bundle y manifiesto con digests y revisión de receta. JRE 21 satisface el mínimo Java 17 de Tomcat 11. La compatibilidad completa del WAR escogido con esta receta se acredita en los ensayos, nunca por la ficha externa. Las versiones concretas son entradas de cada preparación, no constantes inventadas por esta planificación.

**Alternativas:** clonar guest ensayado (arrastra estado/secretos); backup/restore (arrastra configuración); linked clones (dependencia de plantilla); repetir instalación en cada pedido (contradice preparación única). Tomcat 11 se distribuye con archivo oficial fijado y verificado, sin exigir el paquete de Debian 13 en la base Ubuntu existente.

**Fuentes:** código local `infra/services/{build_image.py,sanitize.py,README.md}`; [releases oficiales Draw.io](https://github.com/jgraph/drawio/releases); [compatibilidad Tomcat/Java](https://tomcat.apache.org/whichversion.html). La documentación estable de pct devolvió 403 durante la consulta; la [referencia oficial accesible de pct 9 beta](https://pve.proxmox.com/pve-docs-9-beta/pct.1.html) sólo respalda la elección general de imagen LXC. Las opciones exactas deben validarse contra la versión PVE del staging, usando el camino de creación ya existente.

## 4. Preparación automatizada desde NAP

**Decisión:** nuevo `ensayo_service` y worker durable de ensayos; transporte cerrado a un host de construcción separado. Reutilizar builder, registro institucional, distribución de artefactos y guest runner. Construir primero una imagen limpia y luego crear dos LXC de ensayo desde esa misma imagen. Administración registra comprobación funcional/red y valida/publica por separado.

**Motivo:** `preparacion_service.py` actual hace bootstrap de servicios aprobados; no es un constructor. El orquestador de pedidos está acoplado a pedidos/servicios. Extraer/reutilizar primitivas de ownership, leases y tareas sin crear pedidos o cátedras ficticios. La imagen maestra no se captura desde los ensayos con diagramas o contraseñas.

**Alternativas:** reutilizar literalmente el orquestador académico (acoplamiento incorrecto); seguir con preparación manual externa (contradice aclaración 1).

## 5. Capacidad, expiración y almacenamiento

**Decisión:** extender el ledger existente para propietario académico o recurso de ensayo, exclusivos. Reservar ambos LXC de forma atómica bajo el advisory lock de capacidad existente `4001`. Mantener identidad global de VMID y pool institucional de ensayo. Plazo predeterminado de diseño: 24 h, configurable entre 1 y 168 h; aviso 1 h antes o al iniciar si el plazo es 1 h. El vencimiento cuenta desde que se admite la preparación y se muestra antes de confirmarla.

**Motivo:** el ledger actual exige `pedido_id`; un contador separado permitiría sobreasignar entre ensayos y aprobaciones. Reserva y recurso observado se unen por identidad, sin sumarlos dos veces. Limpieza fallida o resultado incierto retienen capacidad hasta confirmar ausencia. Artefactos conservados siguen ocupando almacenamiento: no se liberan al eliminar LXC. Reservar también el almacenamiento temporal y final del host builder, con presupuesto por trabajo y cuotas de almacenamiento institucional; no confundirlo con CPU/RAM de PVE.

**Alternativas:** ensayos sin reserva (carrera); limpieza manual exclusiva (contradice aclaración 3); TTL sin aviso (sorpresa operativa).

## 6. Incorporación, publicación y versión vigente

**Decisión:** incorporación separada, capaz de contener datos incompletos, vinculada posteriormente a `DefinicionServicio`. Reutilizar estados e inmutabilidad existentes. Una oferta es el perfil `RecursoTemplate` estable: publicar cambia atómicamente su referencia a una definición validada e incrementa su revisión, con una bitácora de publicaciones. No seleccionar la versión por orden lexicográfico ni buscar la máxima entre perfiles distintos.

La selección original del pedido se conserva en snapshot separado; sólo altas pendientes resuelven la versión vigente al evaluar/aprobar. Incluir revisión del perfil, definición, artefactos y capacidad en el token actual. Una publicación concurrente invalida la evaluación con 409 y exige reevaluación administrativa, sin confirmación docente. La aprobación fija snapshot y notificación; renovación y servicios ya aprobados mantienen su versión.

**Motivo:** `DefinicionCreate` exige producto permitido y versión NAP semver; no admite importar fichas arbitrarias o versiones desconocidas. `evaluacion_service.py` ya comprueba perfil/definición y expira token a 60 s. `admision_service.py` ya reevalúa bajo lock y congela snapshots. Publicar definición sola hoy no crea un perfil; el nuevo flujo debe hacerlo explícitamente en la misma transacción de oferta.

**Alternativas:** usar el borrador técnico como caché externo (falsea identidad); actualizar pedidos ya aprobados (rompe historial); aceptar token anterior al cambio (reserva incorrecta).

## 7. Acceso de Draw.io sin cuentas de aplicación

**Decisión:** HTTPS por instancia con nginx y credencial de acceso única en el perímetro HTTP (`access_password`, usuario derivado de UUID), generada después de crear cada LXC, cifrada por el keyring y revelada por el endpoint autorizado existente. Tomcat escucha sólo en loopback; no hay bypass directo desde la red. No son cuentas de Draw.io ni cuentas institucionales de alumnos. No hay almacenado central de diagramas: se prueba archivo editable `.drawio` descargado y reabierto.

**Motivo:** servir una aplicación sin autenticación desde una red compartida no demuestra la denegación de acceso cruzado de SC-003. El perímetro permite usar Draw.io sin desarrollar gestión de cuentas de la aplicación. Credenciales de A no sirven en B; TLS, DNS, IP/MAC y certificados vienen del pool institucional existente. El control administrativo de NAP se mantiene por pertenencia a cátedra. Registrar la exposición deliberada de la credencial por el titular en la guía de uso; no enviar valores por notificaciones.

**Alternativas:** aplicación anónima en la red (no garantiza aislamiento); cuentas internas/SSO de Draw.io o proxy de sesión nuevo del portal (amplían alcance). Los probes HTTP no sustituyen la comprobación funcional del editor.

## 8. Versionado y operación

**Decisión:** conservar manifiestos 1.0 de productos existentes y agregar 1.1 para Draw.io, con validadores seleccionados por `schema_version`; el protocolo guest `nap-guest-runner/1` se mantiene sólo si su forma no cambia, ampliando registros cerrados de producto/parámetros/secretos/resultados. El transporte builder usa un contrato independiente `nap-build-runner/1`. Migraciones Alembic aditivas; no reescribir evidencia ni snapshots históricos. Transportes y registros se despliegan antes de habilitar preparación en UI.

**Motivo:** el manifiesto actual prohíbe campos desconocidos y sólo reconoce tres productos. No abrir esos campos a valores arbitrarios ni invalidar Linux/PostgreSQL/BookStack. URLs y comandos de procedencia viven fuera del manifiesto ejecutable. El registro de artefactos debe poder instalarse/verificarse desde el worker mediante una operación institucional acotada, sin editar configuración manualmente por cada pedido.

## 9. Objetivos operativos y aceptación

**Decisión:** consultas locales/estado con objetivo p95 ≤ 1 s en staging (10 sesiones, 100 muestras); búsqueda externa con deadline total 10 s, una consulta coalescida, cache de índice 15 min y paginación local. Trabajos largos devuelven 202 tras persistir operación. Son objetivos de diseño a medir, no resultados observados. Intentos con pérdida de confirmación reconcilian antes de repetir. Logs correlacionan incorporación/ensayo/operación/definición/recurso sin comandos ejecutables ni secretos; métricas de duración, incertidumbre y limpieza pendiente.

**Motivo:** SC-001/004 exigen recorridos humanos cortos; una petición HTTP no debe esperar un build. SQLite no acredita locks ni carreras: usar PostgreSQL 16. Validación de red, editor, saneamiento, despliegue real y denegación cruzada son gates de staging pendientes.

## Resultado de fase 0

Decisiones de diseño resueltas; sin aclaraciones funcionales pendientes. Precondiciones para aceptar una publicación real: versiones/locks verificados de esa preparación, host builder configurado, dos identidades/redes de ensayo y artefactos registrados. Esto no acredita que esos recursos existan hoy ni que Draw.io esté instalado. La implementación debe aportar las pruebas y evidencia descritas en [quickstart.md](quickstart.md).
