# Reporte de seguridad y aislamiento — Feature 011 (T100)

Fecha: 28/10/2026  
Rama: `011-desplegar-servicios-universitarios`  
Alcance: Auditoría y pruebas adversarias extremo a extremo sobre SSRF, DNS, cookies, headers, imágenes maliciosas, red del nodo y de cátedras, revocación y retención de secretos en DB, spool, journal y archivos operativos.

---

## 1. Resumen de pruebas adversarias y de seguridad

| Suite | Archivo | Casos | Tiempo | Resultado |
|---|---|---|---|---|
| Backend Seguridad y Aislamiento | `backend/tests/test_aislamiento_aplicaciones_011.py` | 35 | 2.17 s | **35/35 Aprobadas** |
| Infra Retención y Políticas | `infra/applications/tests/test_secret_retention.py` | 4 | 0.38 s | **4/4 Aprobadas** |
| Infra Redacción y Red (conjunto) | `infra/applications/tests/` (retención, redacción, red) | 34 | 8.28 s | **34 Aprobadas / 1 Omitida** |

---

## 2. Vectores de ataque evaluados y mitigaciones verificadas

### 2.1 Prevención de SSRF, metadatos y referencias maliciosas
- **Esquemas prohibidos**: Rechazo de cualquier referencia de imagen que contenga `http://`, `https://` o `ssh://` para prevenir abuso de peticiones HTTP arbitrarias.
- **Servicios de metadatos e IPs locales**: Bloqueo de peticiones dirigidas a `169.254.169.254` (metadatos de cloud) o endpoints de loopback.
- **Inyección de comandos y caracteres de control**: Rechazo en validación de esquema de caracteres de shell (`;`, `&`, `|`, `` ` ``, `$`, `(`, `)`, `{`, `}`, `<`, `>`), saltos de línea y bytes nulos (`\x00`).
- **Credenciales en URL**: Prohibición de formatos `user:pass@registry...` en las referencias de imagen del catálogo y formularios.

### 2.2 Blindaje del sistema de archivos y volúmenes (Directory Traversal)
- **Rutas relativas y traversal**: Rechazo de rutas que contengan `.` o `..` (`/../etc/passwd`, `/path/with/../traversal`).
- **Directorios protegidos del sistema host y contenedor**: Bloqueo estricto contra montajes sobre `/sys`, `/proc`, `/dev`, `/boot`, `/root`, `/etc/pve`, `/etc/nap`, `/var/lib/docker`, `/var/run/docker.sock`.
- **Docker socket**: Confirmado que `/var/run/docker.sock` nunca se monta en los contenedores guest de las cátedras, imposibilitando escapes de contenedor hacia el demonio Docker.

### 2.3 Variables de entorno y variables reservadas
- **Variables peligrosas de ejecución**: Rechazo de variables que puedan alterar la vinculación dinámica o el intérprete (`LD_PRELOAD`, `LD_LIBRARY_PATH`, `BASH_FUNC_%%`, `NAP_SECRET_KEY`).
- **No filtración de secretos en catálogo**: Prohibición de campos `password`, `app_key`, `token`, etc., en las variables de entorno públicas del catálogo; deben declararse explícitamente en la lista de secretos protegidos.

### 2.4 Aislamiento estricto entre cátedras (Multi-inquilinato)
- **Denegación pre-I/O**: Docentes de una cátedra que intentan acceder a metadatos de acceso, revelar contraseñas o ejecutar acciones de ciclo de vida (`/stop`, `/restart`) sobre servicios de otra cátedra reciben un error `403 Forbidden` inmediato sin que se realicen consultas o llamadas a infraestructura.
- **Sesiones no autenticadas**: Peticiones anónimas o con sesión expirada son cortadas inmediatamente con `401 Unauthorized` o `403 Forbidden`.

### 2.5 Cifrado en reposo y retención de secretos
- **Keyring del sistema**: Las contraseñas generadas y los valores privados se almacenan cifrados con el keyring del sistema (`credenciales_encrypted`) con contextos únicos por servicio (`servicio:{id}:secretos`). Los snapshots de asignación y metadatos no contienen contraseñas en plano.
- **Ciclo de vida efímero en spool**: El canal de credenciales (`CredentialChannel`) escribe archivos de credenciales con permisos estrictos `0600` dentro de directorios `0700`. Una vez cargadas de manera durable por systemd, los archivos en disco son desvinculados (`unlink`) inmediatamente.
- **Redacción continua de logs**: `SecretRedactor` analiza las salidas de terminal (stdout, stderr, eventos del sistema) y reemplaza todas las representaciones de los secretos (en texto plano, base64, URL-encoded o JSON-escaped) por `[MASK]`, incluso si el secreto queda dividido entre múltiples bloques de lectura contiguos.

### 2.6 Aislamiento de red a nivel de nodo
- **nftables por contenedor**: Cada contenedor cuenta con una tabla de puente exclusiva (`table bridge <id>`).
- **Bloqueo del nodo de gestión**: La política de red descarta explícitamente (`drop`) todo tráfico saliente del contenedor hacia la IP de gestión de Proxmox (`172.16.36.100`), la API de Proxmox (puerto 8006) y las subredes de otras cátedras o nodos.
- **Sin interferencia global**: Las reglas no aplican `flush ruleset`, garantizando que el aislamiento de un contenedor no degrade las reglas ni el tráfico de otros servicios en el nodo.

---

## 3. Conclusión de seguridad

El diseño e implementación cumplen con todos los requerimientos de seguridad, confidencialidad y aislamiento definidos en la especificación 011 y la constitución del proyecto (versión 4.2.0). Ningún secreto se expone en repositorios, logs ni respuestas públicas.

