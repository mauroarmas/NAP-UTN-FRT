# Compuertas iniciales — T007

Fecha: 2026-10-26. Entorno: VM local Proxmox 9.2.2, kernel 7.0.2-6-pve, 4 CPU/8 GB RAM.
**T005/T006 son pruebas reales de factibilidad. Ningún perfil de producción está habilitado.**

| Candidato | Resultado real inicial | Condición para habilitar |
|-----------|------------------------|-------------------------|
| Docker, Ubuntu 24.04, Medium | Factible: pulls público/privado, imagen propia con persistencia, AppArmor/seccomp e aislamiento | Paquete definitivo/versiones cerradas T044; revalidación y entrega por portal T050 |
| Core/MariaDB, Debian 13, Medium | Factible: Core local fijado, snapshot firmado y SELECT 1 local; sin OOM | Perfil/artefactos definitivos y acceso TCP/TLS por cátedra en T061 |
| Core/Caddy, Debian 13, Medium | Factible: release 2.11.7 fijado y HTTP local; sin OOM | Perfil definitivo, gateway y acceso de cátedras en T061 |
| Small | Pendiente de medición propia | No habilitar por extrapolación; Caddy declara 6 GB de disco y no cabe en Small |
| Clúster/red universitarios | Pendiente de instalación e inventario | Datos, permisos, CA, DNS/TLS y aislamiento propios; repetir gates allí |

Docker/MariaDB rozaron el límite de RAM en la instalación (1016,68/1017,28 MiB); Caddy midió
832,73 MiB. Los picos incluyen cachés y no prueban margen para otra aplicación o carga de
estudiantes. El volumen usado quedó dentro de 8 GB en los tres casos. No se inventan mínimos
ni se cambia el tamaño acordado para forzar un resultado.

## Qué quedó acreditado

- Identidad antes de crear; invitado detenido y firewall externo antes de arrancar.
- LXC no privilegiado, UID mapeado, AppArmor y seccomp desde el nodo. Docker sólo añade
  nesting/keyctl exactos; Community conserva esas features desactivadas.
- Fuentes/harness/artefactos congelados y rechazo de helpers, preguntas, descargas u opciones
  no declaradas. Credencial del registry retirada antes de ejecutar la imagen propia.
- Bloqueos de administración/otro invitado con contadores externos positivos, pruebas nativas
  y retirada confirmada de los recursos propios. Draw.io se conservó.

Estos prototipos no acreditan todavía admisión/reservas SQL, recuperaciones del worker,
consola del portal, acceso HTTPS/TCP institucional o el flujo de pedidos de la feature.
Las fixtures, pruebas Bash y carga de Core en Docker están separadas de los recibos de Proxmox.

## Condiciones de parada

Detener la estrategia afectada si cambia un hash/revisión/plataforma, falta una dependencia,
hay una pregunta sin resolver o se propone descargar contenido fuera del plan. Detener también
si requiere LXC privilegiado, unconfined, dispositivos/capabilities/montajes del nodo, excede
Medium o registra OOM. No usar QEMU ni otro tamaño como fallback sin una decisión nueva.

Una identidad distinta, respuesta perdida o ausencia no confirmada exige reconciliación;
no recrear ni liberar contabilidad a ciegas. Sólo retirar recursos con el marcador exacto.
Un perfil pendiente/bloqueado nunca se vuelve disponible por un exit 0 o por encontrar binarios.

## Evidencia

- [Bootstrap](bootstrap-inicial.md) y [recibo de configuración pendiente](bootstrap-nodo-recibo.json).
- [Docker](factibilidad-docker.md) y [recibo real aprobado](docker-cuarto-intento.json).
- [Community/Core](factibilidad-community.md) y [recibo real de ambos pilotos](community-segundo-intento.json).
- Los recibos privados, paquetes y credenciales permanecen fuera de Git. No copiar tokens,
  claves o identidades del laboratorio al entorno universitario.
