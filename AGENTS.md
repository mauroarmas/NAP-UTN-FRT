# Instrucciones y memoria del proyecto NAP

## Preferencias acordadas con Mauro

- **Simplicidad ante todo**. Las cátedras no son técnicas y el administrador sólo un poco más.
  Formularios cortos, lenguaje cotidiano, botones claros y progreso/éxito/error visibles.
- Resolver automáticamente detalles técnicos y reutilizar la configuración inicial.
  No pedir códigos, UUID, hashes, versiones o JSON en los recorridos habituales.
- Implementar directamente correcciones y mejoras acotadas autorizadas. Usar pocas specs:
  sólo ante una funcionalidad importante con decisiones pendientes o a pedido del usuario.
  No iniciar Specify/Plan/Tasks por rutina ni reabrir decisiones ya acordadas.
- No cubrir todas las variantes imaginables: agregar sólo lo necesario para casos reales.
  Conservar seguridad, aislamiento, historial y recuperación sin complejizar la operación diaria.
- Alta de aplicaciones: **elegir → preparar → abrir y comprobar → publicar o eliminar**.
  Sin ensayo de 24 horas ni vencimiento de la preparación/oferta; conservar fechas académicas
  de los pedidos. Al publicar se reutiliza la aplicación para futuras instancias por cátedra.
- Small: 1 vCPU, 512 MB RAM, 4 GB disco. Medium: 2 vCPU, 1024 MB RAM, 8 GB disco.
  Misma base Linux Ubuntu 24.04/LXC; respetar mínimos reales de cada aplicación.
- La cátedra pide aplicación/propósito/fechas y puede elegir **Otro**. Administración aprueba,
  rechaza o pide aclaración; reserva al aprobar, despliega desde la fecha inicial. Sin cuotas
  anticipadas por cátedra. Catálogo administrativo sólo visible para administración.
- No afirmar que una prueba simulada acredita Proxmox real. No compartir secretos en chat ni
  guardarlos en el repositorio. No asumir configurado el clúster/red universitarios.

La fuente normativa es [.specify/memory/constitution.md](.specify/memory/constitution.md),
con el Principio VII agregado el 26/10/2026. Esta memoria se mantiene para próximos chats.

## graphify

Cuando el usuario escriba `/graphify`, usar la habilidad instalada y sus instrucciones antes de
hacer otra cosa. No reconstruir grafos por rutina para cambios acotados.

## Laboratorio de biblioteca operativo (26/10/2026)

- Portal: `http://localhost:5174`. Proxmox local: `172.16.36.100`. Preparador Docker:
  `nap010-builder`, separado del nodo. Arranque habitual: `docker compose up -d`;
  `.env` (ignorado por Git) carga el complemento privado de Compose.
- Archivos privados en `/home/mauro/.local/share/nap010/`. Guía y verificaciones reales:
  [docs/laboratorio-biblioteca.md](docs/laboratorio-biblioteca.md). No imprimir sus secretos.
- Draw.io está **listo para probar**, en dos LXC, con HTTPS y acceso desde esta PC comprobados.
  No se publicó: Mauro puede abrirlo, confirmar funcionamiento y publicar desde el asistente.
- VMware necesita permitir tráfico de los LXC anidados. Se concedió acceso sólo a Mauro sobre
  `/dev/vmnet8`, persistido en el drop-in `90-nap010-permisos.conf` de `vmware.service`.
  No volver a deshabilitarlo mientras se use esta VM para acceder a las aplicaciones.
- Permisos de archivos privados de API/worker: UID 10001; builder/artefactos: root donde corresponde.
  NFS sólo comparte imágenes/recetas/registro con esta PC, no las claves TLS de aplicaciones.
- La red del clúster universitario sigue siendo una instalación distinta: completar sus datos
  reales con infraestructura, sin copiar tokens/certificados/identidades de este laboratorio.
- Para cambios rutinarios, continuar directamente; no crear nuevas specs por esta memoria.
