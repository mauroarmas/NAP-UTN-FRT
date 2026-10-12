# Relevamiento de Requerimientos: Solicitudes de Recursos para Cátedras

Este documento reúne las preguntas clave y decisiones acordadas con el cliente y equipo técnico para el módulo de solicitudes y aprovisionamiento de la **Nube Académica Práctica (NAP - UTN-FRT)**.

---

## 1. Solicitud y Catálogo de Recursos (Paso 1)

1. **Definición de tamaños y especificaciones:**
   - **IaaS:** Los recursos se definen a partir de **plantillas preconfiguradas** (ej. *Small*, *Medium*, *Large* con vCPU, RAM y almacenamiento fijos).
     - *Decisión técnica:* Se requiere un módulo **ABM de Templates de Recursos** para que el Administrador cree, edite y gestione estas plantillas.
   - **SaaS y PaaS:** Una cátedra puede solicitar **cualquier software o servicio**, permitiendo texto y descripción libre de requerimientos (ej: servicios de IA vía API, libros virtuales, Moodle, entornos de desarrollo) para que el administrador evalúe el aprovisionamiento correspondiente.
   - *Estado:* `[x] Resuelto`.

2. **Temporalidad y Vigencia:**
   - **Vigencia del servicio:** Supeditada a la solicitud del usuario cátedra. En el formulario indica el período requerido: rango de fechas (desde/hasta), cuatrimestre (1° o 2°) o ciclo lectivo anual.
   - **Vigencia del pedido:** El pedido como tal no vence de forma automática; permanece en la bandeja administrativa hasta que el Administrador lo resuelva (aprobación, rechazo o solicitud de cambios).
   - *Estado:* `[x] Resuelto`.

---

## 2. Aprobación y Aprovisionamiento Técnico (Pasos 3 y 4)

3. **Rechazo y Solicitud de Ajustes:**
   - **Rechazo definitivo:** El administrador puede rechazar un pedido indicando obligatoriamente un **motivo por escrito**, visible para la cátedra.
   - **Solicitud de cambios / Ajuste:** Si el administrador requiere modificaciones (ej. reducir RAM solicitada por falta de capacidad), el pedido pasa a un estado de revisión/ajuste y vuelve a la cátedra con las observaciones del admin. La cátedra puede aceptar los cambios propuestos o replantear la solicitud.
   - *Estado:* `[x] Resuelto`.

4. **Nivel de Automatización e Infraestructura:**
   - **Infraestructura de despliegue:** Servidores locales on-premise de la UTN-FRT montados en clúster **Proxmox VE** (con alta disponibilidad, almacenamiento NAS compartido y segmentación de red por VLANs/SDN).
   - **Automatización:** El despliegue es **automático** por defecto al aprobar con el template seleccionado.
   - **Opciones avanzadas:** El administrador dispone de una sección de configuración avanzada previa al despliegue por si necesita parametrizar manualmente nodos, subredes o configuraciones específicas de Proxmox.
   - *Estado:* `[x] Resuelto`.

---

## 3. Seguridad, Credenciales y Destinatarios (Paso 5)

5. **Entrega de Credenciales y Roles de Acceso:**
   - **Creación de usuarios del portal:** El administrador gestiona los usuarios de los docentes de cátedra en el portal.
   - **Acceso de alumnos:** Los alumnos **no interactúan con el portal de gestión de NAP**. Únicamente acceden y consumen el servicio o aplicación final una vez desplegada (a través de la URL, IP o credenciales distribuidas por la cátedra).
   - *Estado:* `[x] Resuelto`.

---

## 4. Operación Post-Despliegue (Paso 6)

6. **Autogestión por parte de la Cátedra:**
   - El usuario cátedra dispone de un panel de control para sus servicios activos que incluye:
     - **Visualización de estado:** En línea / Detenido / En despliegue.
     - **Acciones de control:** Botones para **Iniciar**, **Detener** y **Reiniciar** el servicio/contenedor.
     - **Métricas:** Monitoreo básico de uso de recursos (CPU, RAM, disco o métricas de consumo del servicio).
   - *Estado:* `[x] Resuelto`.
