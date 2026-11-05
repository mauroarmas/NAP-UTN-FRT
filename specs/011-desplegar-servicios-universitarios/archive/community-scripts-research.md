# Investigación retirada — Community Scripts

Antecedente del 26/10/2026, fuera del alcance desde el 27/10 por decisión de Mauro.
No implementar ni habilitar estos perfiles; conservar evidencia y código histórico
cuando protege datos. Decisión vigente: [R15](../research.md#r15--docker-hub-como-biblioteca-un-solo-motor-oci).

## R05 — Community Scripts: instalador dentro del invitado, nunca wrapper del nodo

**Decision**: NAP crea el LXC por su orquestación y ejecuta únicamente el instalador de aplicación
`install/<slug>-install.sh`, fijado y empaquetado con Core y un harness institucional común. No
se ejecuta `ct/<slug>.sh` en el nodo ni se usa como alternativa ante un fallo.

**Rationale**: el wrapper host crea sus propios contenedores, arma opciones y redes, puede ofrecer
reintentos o cambios del host y reemplaza la descripción del CT con HTML. Destruiría el marcador
JSON de propiedad de NAP. No se encontró una interfaz documentada para adoptar un CT existente
manteniendo esas garantías. La separación del instalador guest sí está documentada por upstream.

**Alternatives considered**: pasar sólo CTID al wrapper, copiar `bash | curl` en el nodo o envolver
funciones internas del host. Ninguna garantiza identidad, ausencia de doble creación y recuperación.

Revisiones inspeccionadas el 26/10/2026:

- ProxmoxVE: `5d477b0b6efb4141da0b90cadcec32f8641a815c`.
- Core: `81a2e2ae7d42dea39fd5dd7903b266b5e607c811`.

El harness carga el contenido de `lxc/install.func` en `FUNCTIONS_FILE_PATH`, prepara Core local,
fija ambas URLs de fuente a revisiones inmutables y define `_cs_source_func` para archivos del
manifiesto permitido: `lib/tools.func` puede ir a red aunque exista `CORE_DIR`. No carga
`core/build.func` ni `pve/backend.func`. Entorno controlado, sin PTY, stdin cerrado para preguntas,
telemetría/trazas desactivadas, `PASSWORD` no vacío y `SSH_ROOT=no`; se impide personalización
que quite la contraseña o habilite autologin. La capa común de política está versionada y revisada;
no reescribe la instalación de cada aplicación.

Fuentes: [contrato guest de Core](https://github.com/community-scripts/core/blob/81a2e2ae7d42dea39fd5dd7903b266b5e607c811/docs/lxc.md),
[backend host rechazado](https://github.com/community-scripts/core/blob/81a2e2ae7d42dea39fd5dd7903b266b5e607c811/pve/backend.func),
[loader de helpers](https://github.com/community-scripts/core/blob/81a2e2ae7d42dea39fd5dd7903b266b5e607c811/lib/tools.func).

## R06 — Compatibilidad como perfiles comprobables, sin prometer todo el buscador

**Decision**: perfil declarativo con hashes de script/Core/harness, base y OS exactos, recursos,
respuestas permitidas, dependencias bloqueadas por versión/hash, persistencia, acceso, secretos y
pruebas. Los pilotos Community son **MariaDB** y **Caddy**, ambos inicialmente Medium sobre Debian
13. La preferencia Ubuntu se conserva para Docker; no se afirma soporte de Ubuntu de instaladores
que todavía no se comprobó. Ampliar perfiles no necesita escribir otro instalador completo en NAP.

- MariaDB: 1 CPU, 1024 MB, 4 GB upstream; fijar `var_mariadb_phpmyadmin=no`. Agregar configuración
  institucional de base/usuario independiente, TLS y clientes permitidos; el instalador upstream
  no proporciona por sí mismo una cuenta remota segura para la cátedra. Probe autenticado de
  conexión y `SELECT 1`, además de comprobar el acceso de red previsto.
- Caddy: 1 CPU, 512 MB y **6 GB**; no cabe en Small. Fijar `var_caddy_xcaddy=no`, versión exacta
  mediante `var_appversion` y hash del archivo de release. Configuración HTTP interna fija y acceso
  web mediante gateway NAP. El helper Core da prioridad a `var_appversion` incluso si el script
  solicita `latest`.

Fijar commits no congela paquetes APT. El perfil debe identificar un snapshot Debian con Release
verificado y fuentes de paquetes cerradas; ningún `apt upgrade` consulta el repositorio mutable
normal. Descargas de releases pasan por el resolver común que verifica versión y hash del plan de
artefactos aprobado. Dependencia no declarada o pregunta no resuelta bloquea compatibilidad.

**Rationale**: evita repetir el error de etiquetar una ficha como instalable. El alta comercial sólo
se habilita si el perfil técnico está certificado en esa plataforma; no se instala un CT por alta.

**Alternatives considered**: declarar compatibles todos los CT por extensión `.sh`; forzar Ubuntu;
elegir Redis como segundo piloto. Redis fija `trixie` y agrega otro protocolo de autenticación;
Caddy aporta cobertura web con menos adaptación de producto.

Fuentes: [MariaDB](https://github.com/community-scripts/ProxmoxVE/blob/5d477b0b6efb4141da0b90cadcec32f8641a815c/install/mariadb-install.sh),
[Caddy](https://github.com/community-scripts/ProxmoxVE/blob/5d477b0b6efb4141da0b90cadcec32f8641a815c/install/caddy-install.sh),
[helper releases](https://github.com/community-scripts/core/blob/81a2e2ae7d42dea39fd5dd7903b266b5e607c811/lib/forge.func),
[Debian Snapshot](https://snapshot.debian.org/).
