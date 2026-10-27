# Prompt para Claude al clonar el repositorio

Copiar el bloque siguiente en el chat del agente, desde la raíz del clon:

```text
Vas a continuar la implementación de NAP, un pequeño AWS simple para la universidad.
Trabajá sobre la rama 011-desplegar-servicios-universitarios y la spec existente 011.

Leé primero CLAUDE.md, AGENTS.md y docs/traspaso-011.md. Después leé la constitución
y spec.md, plan.md, tasks.md, contracts/ y quickstart.md de specs/011-desplegar-servicios-universitarios/.
Usá .claude/skills/speckit-implement/SKILL.md para continuar, sin regenerar la spec.

Antes de modificar, inspeccioná git status, la revisión Alembic y la configuración
local. No supongas que tengo la VM, red, rutas privadas o credenciales de Mauro.
Ayudame a iniciar el portal con docker-compose.handoff.yml y, si recibí la copia
privada, restaurarla mediante scripts/traspaso.py siguiendo el traspaso. No muestres
ni subas secretos. Sin copia, migrá una DB vacía y usá el bootstrap interactivo.

El avance registrado es 38/105; hay código parcial en tareas aún sin marcar.
El último ensayo del runtime definitivo Docker falló antes de arrancar porque
Proxmox agregó net0.type=veth. Ya está corregido y probado en el repositorio,
pero falta distribuirlo y completar el gate real. El ensayo quedó incierto;
se retiraron CT/discos/pool temporales y se conservó el historial. No repitas
esa ejecución ni reutilices su identidad. Reconciliá de forma segura primero.
Los perfiles definitivos siguen deshabilitados. Draw.io e IaaS usan el legado:
no los elimines ni los reescribas innecesariamente.

Empezá identificando el siguiente bloque pendiente y sus dependencias, aprovechando
lo ya implementado. Priorizá cerrar Docker real y luego Community MariaDB/Caddy,
pedidos/programación, consola de lectura y recuperación según tasks.md. No habilites
perfiles por fixtures ni debilites controles para aprobar el ensayo.

Simplicidad ante todo: agregar una oferta no instala ni reserva; instalar/verificar
ocurre al desplegar el pedido aprobado. Sin preparar/publicar manualmente, sin
ensayos de 24h. Cátedra pide aplicación/propósito/fechas, admin elige tamaño.
Conservá Small 1 CPU/512 MB/4 GB y Medium 2 CPU/1 GB/8 GB con mínimos reales.

Ejecutá pruebas proporcionales al bloque, conservá seguridad/datos/recuperación
y distinguí dobles de Proxmox real. Actualizá tasks/evidencia sólo con lo verificado.
Los autocommits están habilitados: revisá el diff y no incluyas datos privados.
Avanzá con decisiones rutinarias y consultame sólo si falta información necesaria
del nuevo entorno o hay una decisión de producto sin resolver.
```
