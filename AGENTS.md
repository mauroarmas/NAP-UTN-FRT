# Instrucciones y memoria del proyecto NAP

## Estado de implementación 011 (28/10/2026)

Feature 011 (desplegar servicios universitarios vía OCI) está implementada y validada de extremo a extremo
en el laboratorio local (95/95 tareas activas completadas más las 9 tareas de convergencia `T106`–`T114`;
10 tareas históricas de Community Scripts retiradas el 27/10/2026). El alcance consolidado comprende
Docker Hub como biblioteca de aplicaciones y referencias de imágenes propias en registries autorizados
sobre un único motor Docker en LXC Ubuntu 24.04 no privilegiado. El perfil `docker-ubuntu24:1`
(`sha256: 2ed42514102e2f2ed7702bf4f1162f4ba2b6c175f2012f929c0895e743f67a24`, `policy_digest: 73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2`,
plataforma PVE `9.2.2` / kernel `7.0.2-6-pve`) fue validado con la compuerta real en Proxmox (`172.16.36.100`)
para `traefik/whoami` y `campus-demo` y quedó habilitado de forma idéntica en `/etc/nap/applications-011/runner.json`
y en `settings.json` del portal. Documentación operativa y evidencias en `docs/evidencia/011/` y `docs/despliegue-aplicaciones.md`.

## Preferencias acordadas con Mauro

- **Propósito del producto: un pequeño AWS simple para la universidad.** Docker Hub es la
  biblioteca de aplicaciones; también se admiten referencias de imágenes propias en registries
  autorizados. Ambas entradas reutilizan un único motor Docker/OCI. **Community Scripts se retiró
  del alcance el 27/10/2026**; no implementar Core/harness o pilotos por esa vía. IaaS conserva
  Ubuntu/Debian. El runtime genérico está parcialmente construido y pendiente del gate real.

- **Simplicidad ante todo**. Las cátedras no son técnicas y el administrador sólo un poco más.
  Formularios cortos, lenguaje cotidiano, botones claros y progreso/éxito/error visibles.
- El acceso a servicios no incluye formularios de evidencia institucional, JSON, UUID ni fechas UTC.
  Conservar las comprobaciones automáticas y el historial sin trámites manuales para el administrador.
- Resolver automáticamente detalles técnicos y reutilizar la configuración inicial.
  No pedir códigos, UUID, hashes, versiones o JSON en los recorridos habituales.
- Implementar directamente correcciones y mejoras acotadas autorizadas. Usar pocas specs:
  sólo ante una funcionalidad importante con decisiones pendientes o a pedido del usuario.
  No iniciar Specify/Plan/Tasks por rutina ni reabrir decisiones ya acordadas.
- No cubrir todas las variantes imaginables: agregar sólo lo necesario para casos reales.
  Conservar seguridad, aislamiento, historial y recuperación sin complejizar la operación diaria.
- **Pruebas proporcionales al cambio** (acordado con Mauro): durante el desarrollo ejecutar sólo
  las pruebas afectadas, una vez por bloque; repetirlas si hay cambios relevantes o fallos.
  Reservar la regresión completa para un hito importante o la entrega, sin repetirla por fase.
  Probar en Proxmox cuando cambien despliegue, red o permisos. Conservar pruebas críticas de
  seguridad, datos y recuperación; no eliminar cobertura útil para reducir el tiempo de ejecución.
- Alta de aplicaciones: **elegir → agregar → disponible para solicitar**, sin crear instancias ni
  reservar capacidad. La instalación y comprobación son automáticas al desplegar el pedido aprobado;
  no volver a introducir pasos manuales de preparar, confirmar y publicar.
  Sin ensayo de 24 horas ni vencimiento de la preparación/oferta; conservar fechas académicas
  de los pedidos. Al publicar se reutiliza la aplicación para futuras instancias por cátedra. No se ofrecen aplicaciones sin adaptador compatible.
- Small: 1 vCPU, 512 MB RAM, 4 GB disco. Medium: 2 vCPU, 1024 MB RAM, 8 GB disco.
  Docker conserva la base Ubuntu 24.04/LXC; IaaS ofrece Ubuntu 24.04 y Debian 13.
  Respetar mínimos reales. El candidato Docker inicial es Medium hasta validar Small.
- La cátedra pide aplicación/propósito/fechas y puede elegir **Otro**. Administración aprueba,
  rechaza o pide aclaración; reserva al aprobar, despliega desde la fecha inicial. Sin cuotas
  anticipadas por cátedra. Catálogo administrativo sólo visible para administración.
- No afirmar que una prueba simulada acredita Proxmox real. No compartir secretos en chat ni
  guardarlos en el repositorio. No asumir configurado el clúster/red universitarios.

La fuente normativa es [.specify/memory/constitution.md](.specify/memory/constitution.md),
versión 4.2.0, con la distinción entre oferta e instancia acordada el 26/10/2026. Esta memoria se mantiene para próximos chats.

## graphify

Cuando el usuario escriba `/graphify`, usar la habilidad instalada y sus instrucciones antes de
hacer otra cosa. No reconstruir grafos por rutina para cambios acotados.

## Laboratorio de biblioteca operativo (26/10/2026)

- Portal: `http://localhost:5174`. Proxmox local: `172.16.36.100`. Preparador Docker:
  `nap010-builder`, separado del nodo. Arranque habitual: `docker compose up -d`;
  `.env` (ignorado por Git) carga el complemento privado de Compose.
- Archivos privados en `/home/mauro/.local/share/nap010/`. Guía y verificaciones reales:
  [docs/laboratorio-biblioteca.md](docs/laboratorio-biblioteca.md). No imprimir sus secretos.
- Draw.io está **disponible en el catálogo**. Los LXC auxiliares se retiraron al completar el alta.
  Ubuntu 24.04 y Debian 13 aparecen automáticamente desde Proxmox y admiten pedidos.
  La red IaaS local usa el perfil privado `lab-linux-010` (direcciones .71–.78).
- VMware necesita permitir tráfico de los LXC anidados. Se concedió acceso sólo a Mauro sobre
  `/dev/vmnet8`, persistido en el drop-in `90-nap010-permisos.conf` de `vmware.service`.
  No volver a deshabilitarlo mientras se use esta VM para acceder a las aplicaciones.
- Permisos de archivos privados de API/worker: UID 10001; builder/artefactos: root donde corresponde.
  NFS sólo comparte imágenes/recetas/registro con esta PC, no las claves TLS de aplicaciones.
- La red del clúster universitario sigue siendo una instalación distinta: completar sus datos
  reales con infraestructura, sin copiar tokens/certificados/identidades de este laboratorio.
- Para cambios rutinarios, continuar directamente; no crear nuevas specs por esta memoria.

- Migración `010_05_alta_materializada`: repara la constraint antigua que impedía vincular
  un pedido ALTA con su servicio creado, aunque las revisiones anteriores ya figuraban aplicadas.
- Seguimiento de despliegue: barra de cuatro etapas en Pedidos, actualización automática y campana
  de avisos. Distinguir instancia iniciada/acceso pendiente de servicio disponible; no simular porcentajes
  de tiempo. Draw.io ahora se abre con la sesión de NAP desde Ver acceso, mediante un gateway HTTPS
  separado por instancia. No copiar contraseñas del portal al guest ni alojar el editor en el origen del portal.
- Gateway local: `nap010-app-gateway`, `https://app-<servicio>.nap-apps.test:8443`, sólo loopback.
  Configuración/clave TLS privadas en nap010; nombres locales 1–256 en /etc/hosts con respaldo privado.
  Sesión de aplicación revocable, códigos de un uso y sin service workers; ver docs/acceso-aplicaciones-nap.md.
