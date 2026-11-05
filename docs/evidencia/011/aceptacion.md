# Aceptación integrada y criterios de éxito — Feature 011 (T103)

Fecha: 28/10/2026  
Rama: `011-desplegar-servicios-universitarios`  
Alcance: Consolidación de los Criterios de Éxito SC-001 al SC-009 definidos en la especificación, con medidas observadas, enlaces de trazabilidad y diferenciación explícita entre resultados de laboratorio y requisitos pendientes para la red institucional universitaria.

---

## 1. Matriz de Criterios de Éxito (SC-001 a SC-009)

| Criterio | Requisito medible | Resultado observado | Evidencia técnica | Estado |
|---|---|---|---|---|
| **SC-001** | Alta de ofertas OCI en catálogo (Hub o propia) en <=3 min, sin terminal ni pasos manuales de preparación/publicación. | Alta completada en UI en **~45 s**; formulario unificado OCI precargado; oferta inmediatamente disponible para solicitar sin CTs previos. | `docs/evidencia/011/us1-imagenes.md`<br>`docs/evidencia/011/us2-biblioteca.md` | **Cumplido** |
| **SC-002** | Demostración de dos aplicaciones con único motor: `traefik/whoami` (Hub) y `campus-demo` (propia privada con persistencia). | Un solo motor Docker validado en el nodo Proxmox real (`172.16.36.100`, PVE `9.2.2`, kernel `7.0.2-6-pve`, `policy_digest = 73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2`) con `traefik/whoami` (`execution_id: 4bba6281-3a9a-40ef-891d-49e122729537`) y `172.16.36.1:5443/nap/campus-demo` (`execution_id: d07d3250-aba2-463f-8ce6-b8c20e7e806c`, registry privado autenticado y persistencia en `/data` verificada tras reinicio de contenedor), con limpieza completa de `LXC 900011` y habilitación sincronizada de `docker-ubuntu24:1` (`sha256: 2ed42514102e2f2ed7702bf4f1162f4ba2b6c175f2012f929c0895e743f67a24`). | `docs/evidencia/011/factibilidad-docker.md`<br>`docs/evidencia/011/us1-imagenes.md`<br>`docs/evidencia/011/perfil-docker.md` | **Cumplido (laboratorio Proxmox real)** |
| **SC-003** | Dos cátedras con instancias de la misma oferta aisladas; 100% de intentos de acceso cruzado denegados (403); stop/delete no afecta al par. | 100% (7/7) de intentos cruzados rechazados con 403; VMIDs, IPs y secretos disjuntos; stop sobre servicio A mantiene servicio B en `running`. | `backend/tests/test_aislamiento_aplicaciones_011.py`<br>`backend/tests/test_regresion_servicios_011.py` | **Cumplido** |
| **SC-004** | Consola con 2 trabajos simultáneos: captura→pantalla p95 <=5 s, apertura <=3 s, límite 10 MB/30 días sin filtrar secretos. | Captura→pantalla **p95 = 0.0795 s**; apertura = **0.0122 s**; cuota de 10 MB respetada; 0 secretos en texto de consola o base de datos. | `docs/evidencia/011/us4-consola.md`<br>`infra/laboratorio/011/medir_consola.py` | **Cumplido** |
| **SC-005** | Reconciliación tras cortes o reinicios: sin duplicar CT ni reserva de capacidad; estado incierto nunca se anuncia como entregado. | Recuperación confirmada: el worker inspecciona marcadores y tareas de PVE sin relanzar el instalador; probe fallido retiene entrega; no hay CT duplicado. | `docs/evidencia/011/us5-recuperacion.md`<br>`backend/tests/test_recuperacion_aplicaciones_011.py` | **Cumplido** |
| **SC-006** | Fallo, reintento y baja: todo recurso vinculado a pedido; ausencia confirmada antes de liberar red/ledger; limpieza pendiente visible ante error. | `vzdestroy` fallido mantiene identidad y contabilidad bloqueadas; reintento vía `POST /operaciones/{id}/reintentar` crea `reparar` sin duplicidad. | `backend/tests/test_ciclo_vida_aplicaciones_011.py`<br>`backend/tests/postgres/test_reintentos_011.py` | **Cumplido** |
| **SC-007** | Protección de secretos y terminal segura: 0 secretos en spool/journal/DB/export; texto plano seguro (sin XSS ni ANSI); 403 limpia buffer. | Cero secretos filtrados en exportaciones ni logs; inputs con XSS y ANSI mostrados como texto literal; pérdida de autorización revoca inmediatamente. | `docs/evidencia/011/seguridad.md`<br>`frontend/tests/e2e/despliegue-aplicaciones.spec.js` | **Cumplido** |
| **SC-008** | Solicitud docente simple en <=2 min (aplicación, fechas, propósito); opción «Otro» con imagen/instrucciones opcionales sin gestionar infra. | Formulario docente completado en **~30 s**; opción «Otro» sin selección de hardware; reserva atómica diferida a la aprobación del admin. | `docs/evidencia/011/us3-pedidos.md`<br>`frontend/tests/pedidos-otro-aplicacion.test.jsx` | **Cumplido** |
| **SC-009** | Regresión transversal: IaaS Ubuntu/Debian, Draw.io 010 y renovaciones intactas sin recrear instancias; evidencia diferenciada por entorno. | 5 pruebas backend y 4 E2E aprobadas; renovación extiende vigencia conservando contenedor, VMID, IP y secretos; entornos documentados. | `docs/evidencia/011/regresion.md`<br>`docs/despliegue-aplicaciones.md` | **Cumplido** |

---

## 2. Diferenciación de entornos: Laboratorio vs. Red Universitaria

Siguiendo la constitución del proyecto y los acuerdos con Mauro:
1. **Resultados de laboratorio local (Acreditados)**:
   - Hipervisor Proxmox VE 9.2.2 en `172.16.36.100` sobre VM VMware.
   - Perfil de red privado `lab-linux-010` (segmento `172.16.36.0/24`, slots `.81` a `.88`).
   - Gateway de aplicaciones local en `https://app-<id>.nap-apps.test:8443` con loopback.
   - Base de datos PostgreSQL de prueba aislada en `:55432`.
   - Todos los ensayos automatizados (97 backend, 50 infra, 22 postgres, 22 vitest, 6 playwright) se ejecutaron y aprobaron en este laboratorio.
2. **Requisitos pendientes para la Red Universitaria (No simulados como terminados)**:
   - Asignación de rangos de red e interfaces troncales VLAN en los switches del centro de cómputos.
   - Emisión de certificados TLS institucionales reconocidos para `*.universidad.edu.ar`.
   - Conexión del portal al clúster Proxmox de producción con almacenamiento distribuido (Ceph / NFS institucional).
   - Configuración del registry institucional de imágenes con cuentas de servicio corporativas.
   - Ninguna clave, certificado ni token de la PC de Mauro debe trasladarse al entorno institucional.

---

## 3. Estado de Aceptación y Bloqueos Pendientes

- **Verificado en laboratorio automatizado**: Los flujos de alta declarativa (SC-001), aislamiento entre cátedras (SC-003), consola en vivo y límites (SC-004), reconciliación y recuperación (SC-005, SC-006), resguardo de secretos (SC-007), solicitud docente (SC-008) y no regresión de IaaS/Draw.io (SC-009) están verificados mediante pruebas automatizadas.
- **Compuerta física Proxmox completada (`SC-002`, `T044`–`T047`, `T050`, `T106`, `T108`, `T109`)**: Distribuido el paquete definitivo (`policy_digest = 73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2`) y aprobadas las dos ejecuciones reales en Proxmox (`traefik/whoami` y `campus-demo`) mediante `infra/laboratorio/011/validar_motor_docker.py`, el perfil `docker-ubuntu24:1` (`sha256: 2ed42514102e2f2ed7702bf4f1162f4ba2b6c175f2012f929c0895e743f67a24`) quedó habilitado de forma idéntica en `/etc/nap/applications-011/runner.json` (nodo) y `settings.json` (portal). La instalación en la red institucional universitaria requerirá su propia validación física y certificados corporativos.

