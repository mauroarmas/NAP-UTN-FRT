# Dudas abiertas para la entrevista

Archivo vivo. Cada duda tiene el **por qué importa** (qué parte del sistema cambia según
la respuesta) y un espacio para anotar lo que se defina. Marcá `[x]` cuando quede resuelta
y escribí la respuesta abajo; después la convertimos en spec o en enmienda de la
constitución según corresponda.

Prioridad: 🔴 bloquea trabajo en curso · 🟡 define alcance próximo · 🟢 bueno saberlo.

---

## 1. Acceso al contenedor y despliegue de software

### 🔴 1.1 ¿La cátedra debe poder entrar por terminal a su propio contenedor?

- [ ] Resuelta

**Por qué importa:** es la duda que frenó la consola embebida. Hoy la cátedra puede prender,
apagar y reiniciar, pero no entrar. Si la respuesta es "sí", hay que terminar la consola del
portal (o definir SSH). Si es "no", la cátedra solo pide y el admin ejecuta, y sacamos la
funcionalidad del alcance para siempre.

**Sub-preguntas:**
- Si entra: ¿terminal embebida en el portal, o SSH directo con su propio usuario?
- ¿Quién crea y entrega el usuario/contraseña de adentro del contenedor?
- ¿Entra con root o con un usuario sin privilegios?

**Respuesta:**

> _(pendiente)_

---

### 🔴 1.2 ¿Cómo se despliega una base de datos o una aplicación en el contenedor de una cátedra?

- [ ] Resuelta

**Por qué importa:** define si el portal es "te doy un contenedor vacío y arreglate" o
"te doy un servicio ya andando". Cambia el modelo de templates y probablemente agrega un
tipo de pedido nuevo.

**Opciones sobre la mesa:**
- **a)** La cátedra lo hace ella misma (⇒ necesita acceso del punto 1.1).
- **b)** Lo pide al admin y el admin lo instala (⇒ hace falta un flujo de "pedido de
  instalación", distinto del pedido de contenedor).
- **c)** Se resuelve con templates preconfigurados por tipo (ej. "LXC + PostgreSQL",
  "LXC + Node") y la cátedra elige del catálogo (⇒ hay que armar y mantener ese catálogo).

**Respuesta:**

> _(pendiente)_

---

### 🟡 1.3 ¿Quién mantiene el software una vez instalado (updates, parches)?

- [ ] Resuelta

**Por qué importa:** si es el admin, hace falta prever ventanas de mantenimiento y aviso a
las cátedras. Si es la cátedra, vuelve a depender del acceso del punto 1.1.

**Respuesta:**

> _(pendiente)_

---

## 2. Ciclo de vida de los servicios

### 🟡 2.1 ¿Los servicios tienen vencimiento por cuatrimestre / año lectivo?

- [ ] Resuelta

**Por qué importa:** hoy un servicio desplegado vive indefinidamente y sigue consumiendo
cuota. Si hay vencimiento, hace falta fecha de fin en el pedido, avisos previos y una
política de qué pasa al vencer.

**Sub-preguntas:**
- ¿Qué pasa al terminar la cursada: se apaga, se borra, se archiva?
- ¿Se avisa antes? ¿Con cuánta anticipación?
- ¿La cátedra puede pedir prórroga?

**Respuesta:**

> _(pendiente)_

---

### 🟡 2.2 ¿Qué pasa con los datos cuando un servicio se da de baja?

- [ ] Resuelta

**Por qué importa:** hoy la baja es lógica en el portal (el registro queda para el histórico)
pero el contenedor se libera en Proxmox y los datos se pierden. Si hace falta conservarlos,
hay que definir backup/export antes de liberar.

**Respuesta:**

> _(pendiente)_

---

### 🟢 2.3 ¿Hay backups de los contenedores? ¿Quién los pide y quién los restaura?

- [ ] Resuelta

**Por qué importa:** Proxmox tiene backup nativo. Si es una función esperada, es una feature
del portal (pedir backup / restaurar); si no, hay que decirlo explícito para que la cátedra
no lo asuma.

**Respuesta:**

> _(pendiente)_

---

## 3. Cuotas y recursos

### 🟡 3.1 ¿Quién define la cuota de cada cátedra y con qué criterio?

- [ ] Resuelta

**Por qué importa:** hoy la cuota es un número que carga el admin a mano. Si hay un criterio
(cantidad de alumnos, tipo de materia, etc.) puede sugerirse automáticamente.

**Respuesta:**

> _(pendiente)_

---

### 🟡 3.2 ¿Qué hace una cátedra que necesita más recursos de los que tiene asignados?

- [ ] Resuelta

**Por qué importa:** hoy el pedido simplemente se rechaza por cuota excedida, sin salida.
Si debe existir un camino (pedir ampliación, préstamo temporal para un parcial), es una
feature nueva.

**Respuesta:**

> _(pendiente)_

---

### 🟢 3.3 ¿Se puede redimensionar un servicio ya desplegado (más RAM, más disco)?

- [ ] Resuelta

**Por qué importa:** hoy no existe. Proxmox lo permite en caliente para algunos recursos.
¿Lo pide la cátedra? ¿Lo ejecuta el admin?

**Respuesta:**

> _(pendiente)_

---

## 4. Usuarios y permisos

### 🟡 4.1 ¿Cuántas personas por cátedra usan el portal, y con qué roles?

- [ ] Resuelta

**Por qué importa:** hoy el modelo asume un usuario por cátedra. Si entran titular, JTP y
ayudantes, puede hacer falta distinguir quién pide y quién solo mira.

**Sub-preguntas:**
- ¿Los alumnos entran al portal, o solo docentes?
- ¿Alguien puede pedir en nombre de la cátedra sin poder apagar/prender?

**Respuesta:**

> _(pendiente)_

---

### 🟢 4.2 ¿Qué pasa cuando cambia el docente a cargo de una cátedra?

- [ ] Resuelta

**Por qué importa:** los servicios quedan asociados a la cátedra, pero el usuario es
personal. Define si hace falta transferencia o baja/alta de usuarios.

**Respuesta:**

> _(pendiente)_

---

## 5. Red y acceso al servicio desplegado

### 🔴 5.1 ¿Cómo llega un alumno a la aplicación que desplegó su cátedra?

- [ ] Resuelta

**Por qué importa:** es el agujero más grande del modelo actual. El portal despliega el
contenedor pero no dice nada de cómo se lo alcanza. Cambia si hace falta IP pública, DNS,
reverse proxy o VPN.

**Sub-preguntas:**
- ¿Solo desde la red de la facultad, o también desde afuera?
- ¿Cada servicio tiene un nombre/URL, o se accede por IP?
- ¿Hace falta abrir puertos? ¿Quién los abre?

**Respuesta:**

> _(pendiente)_

---

### 🟡 5.2 ¿La cátedra necesita saber la IP de su servicio, o se le abstrae?

- [ ] Resuelta

**Por qué importa:** hoy el portal muestra la IP. Si el modelo es "no técnico", quizá
convenga mostrar una URL amigable en su lugar.

**Respuesta:**

> _(pendiente)_

---

## 6. Operación y expectativas

### 🟡 6.1 ¿Hay horario de atención / tiempo de respuesta esperado para aprobar un pedido?

- [ ] Resuelta

**Por qué importa:** define si hacen falta notificaciones (mail, aviso en el portal) o si
alcanza con que el admin mire la lista cuando puede.

**Respuesta:**

> _(pendiente)_

---

### 🟢 6.2 ¿Qué información le sirve realmente a la cátedra en el panel de métricas?

- [ ] Resuelta

**Por qué importa:** hoy se muestran CPU/RAM/disco, que es lo que da Proxmox. Para una
cátedra no técnica quizá sea más útil "está andando / no está andando" y poco más.

**Respuesta:**

> _(pendiente)_

---

### 🟢 6.3 ¿Se avisa a la cátedra cuando su servicio se cae o se apaga solo?

- [ ] Resuelta

**Por qué importa:** hoy no hay alertas. Define si hace falta monitoreo activo o alcanza con
que lo vea al entrar.

**Respuesta:**

> _(pendiente)_

---

## Estado del trabajo bloqueado por estas dudas

| Duda | Qué está frenado |
|------|------------------|
| 1.1 | Consola embebida (spec 003, US3) — código en pausa, ver más abajo |
| 1.2 | Modelo de templates / posible tipo de pedido nuevo |
| 5.1 | No hay ninguna feature de acceso al servicio desplegado |

### Nota sobre la consola (spec 003, US3)

Quedó **en pausa** el 2026-08-15, a la espera de la duda 1.1:

- La cátedra **no** tiene acceso a consola. El botón se sacó de la pestaña Servicios y el
  endpoint `POST /servicios/{id}/console-ticket` quedó restringido a administrador.
- El **admin** sí tiene un botón "🖥️ Consola" que abre la consola nativa de Proxmox en otra
  pestaña. Requiere que el admin tenga sesión propia en Proxmox — es un atajo para él, no
  una vía de acceso para la cátedra.
- El código del proxy WebSocket (`ConsolaServicio.jsx` + la ruta `/servicios/{id}/console`)
  **sigue en el repo pero sin uso**, por si la respuesta a 1.1 es que sí hace falta.
- Motivo técnico del freno: el relay conecta y autentica bien contra Proxmox, pero la sesión
  muere sin transmitir datos. Hipótesis principal **sin confirmar**: Proxmox no acepta API
  tokens para el websocket de consola y hace falta un ticket de sesión
  (`POST /access/ticket` con usuario y contraseña). No se pudo probar porque en el `.env`
  solo hay token, no contraseña.
