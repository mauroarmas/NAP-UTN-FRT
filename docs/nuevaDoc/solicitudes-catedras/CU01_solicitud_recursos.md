# Caso de Uso Principal: Solicitud y Aprovisionamiento de Recursos para Cátedras

## 1. Información General

| Campo | Detalle |
| :--- | :--- |
| **Identificador** | CU-01 |
| **Nombre** | Solicitud y Aprovisionamiento de Recursos de Infraestructura y Servicios (Happy Path y Variantes) |
| **Sistema** | Nube Académica Práctica (NAP) — UTN Facultad Regional Tucumán |
| **Actores** | **Usuario Cátedra** (Docente responsable de cátedra)<br>**Administrador** (Operador de Infraestructura / TI de la NAP)<br>**Sistema / Orquestador Proxmox VE** (Servidores locales UTN-FRT) |
| **Objetivo** | Permitir que una cátedra solicite recursos bajo demanda (IaaS, PaaS o SaaS) especificando su necesidad y vigencia, y que el Administrador evalúe la solicitud, asigne o ajuste la plantilla correspondiente y autorice el aprovisionamiento automatizado en el clúster local de Proxmox VE hasta dejarlo disponible para su consumo. |
| **Precondiciones** | 1. El usuario de cátedra cuenta con usuario activo y autenticado en el portal.<br>2. El sistema cuenta con templates preconfigurados gestionados por el Administrador (IaaS: Small, Medium, Large; SaaS/PaaS: servicios base).<br>3. El clúster local Proxmox VE dispone de conectividad y capacidad de cómputo/almacenamiento. |
| **Postcondiciones** | 1. El pedido queda registrado y en estado `DISPONIBLE`.<br>2. El contenedor/VM/servicio queda instanciado y operativo en la infraestructura local.<br>3. Se generan los datos de acceso (URL, IP, puerto o token de API) visibles para la cátedra en su panel.<br>4. La cátedra puede realizar acciones de autogestión (Iniciar, Detener, Reiniciar) y visualizar métricas de uso.<br>5. Queda registrada la trazabilidad y fecha de vigencia del servicio. |

---

## 2. Tipos de Servicios Soportados

1. **IaaS (Infraestructura como Servicio):**
   - Contenedores (LXC) y Máquinas Virtuales (VMs) sobre Proxmox VE.
   - Tamaños predefinidos mediante templates administrables (ej. *Small*, *Medium*, *Large* con vCPU, RAM y disco fijos).
   - El Administrador gestiona estos templates mediante un módulo ABM de plantillas.
2. **SaaS (Software como Servicio):**
   - Aplicaciones completas listas para usar (ej. Libro Virtual interactivo, Moodle, JupyterHub cátedra, herramientas de laboratorio).
   - La cátedra puede solicitar cualquier software o servicio institucional mediante descripción de requerimientos.
3. **PaaS (Plataforma como Servicio):**
   - Servicios y plataformas accesibles vía API (ej. APIs de inferencia de Inteligencia Artificial locales, bases de datos gestionadas PostgreSQL/MySQL).
   - Consumo directo mediante tokens o endpoints provistos por el sistema.

---

## 3. Flujo Principal (Happy Path)

1. **Selección y Configuración de la Solicitud:**
   - El Usuario Cátedra ingresa al portal de autoservicio y selecciona **Nuevo Pedido**.
   - Selecciona el tipo de servicio deseado (**IaaS**, **SaaS** o **PaaS**).
   - Para IaaS: selecciona el template base de recursos (*Small*, *Medium*, *Large*).
   - Para SaaS / PaaS: describe detalladamente el software o servicio requerido y los recursos estimados.
   - Indica la **vigencia requerida**: rango de fechas (desde/hasta), cuatrimestre académico o ciclo lectivo anual.
   - Envía el pedido.
2. **Creación y Registro del Pedido:**
   - El Sistema valida los campos obligatorios y persiste la solicitud con estado `PENDIENTE`.
   - El pedido queda disponible en la bandeja de gestión del Administrador.
3. **Revisión del Administrador:**
   - El Administrador visualiza el listado de pedidos pendientes en su consola.
   - Analiza los requerimientos técnicos, la vigencia solicitada y la disponibilidad de recursos en el clúster Proxmox VE.
   - Selecciona la plantilla de aprovisionamiento idónea (pudiendo consultar o modificar parámetros en la sección de *Opciones Avanzadas* si requiere personalización de red o almacenamiento).
4. **Aprobación y Aprovisionamiento:**
   - El Administrador confirma la **Aprobación**.
   - El Sistema actualiza el estado a `EN_DESPLIEGUE` y despacha la orden al orquestador del clúster local de Proxmox VE.
   - Proxmox VE clona la plantilla/contenedor/VM, asigna la red VLAN/SDN y levanta el servicio de forma automática.
   - Al finalizar, el orquestador retorna los datos de conexión (IP interna/externa, URL de acceso, credenciales o tokens de API).
5. **Puesta a Disposición y Notificación:**
   - El Sistema actualiza el estado del pedido a `DISPONIBLE` y asocia el nuevo `Servicio` activo a la cátedra solicitante.
   - Se notifica a la cátedra (vía notificación interna en el portal y/o correo institucional) informando que el recurso está listo para ser utilizado.
6. **Visualización y Autogestión por la Cátedra:**
   - El Usuario Cátedra ingresa a la sección **Mis Servicios** en el portal.
   - Visualiza el servicio en estado `ACTIVO / DISPONIBLE`, su fecha de vigencia y los datos de acceso (URL, IP y credenciales).
   - La cátedra puede distribuir los enlaces a sus alumnos (quienes consumen directamente la aplicación sin ingresar al portal NAP).
   - La cátedra dispone de controles de autogestión: **Iniciar**, **Detener**, **Reiniciar** y monitoreo de métricas de consumo (CPU, RAM, disco).

---

## 4. Diagrama de Secuencia: Happy Path

```mermaid
sequenceDiagram
    autonumber
    actor Catedra as Usuario Cátedra
    participant UI as Portal NAP (Frontend)
    participant Backend as API Backend
    participant DB as Base de Datos
    actor Admin as Administrador
    participant Proxmox as Clúster Proxmox VE (Local UTN-FRT)

    %% Paso 1 y 2: Solicitud
    rect rgb(240, 248, 255)
        Note over Catedra, DB: 1 y 2: Creación del Pedido con Vigencia
        Catedra->>UI: Completa formulario de solicitud<br/>(Tipo: IaaS/SaaS/PaaS, Template/Descripción, Vigencia)
        UI->>Backend: POST /pedidos {tipo, templateSugerido, descripcion, vigencia}
        Backend->>DB: INSERT Pedido (estado: "PENDIENTE", vigencia, cátedra_id)
        DB-->>Backend: Pedido registrado (id, estado: "PENDIENTE")
        Backend-->>UI: 201 Pedido Creado
        UI-->>Catedra: Muestra confirmación y número de seguimiento
    end

    %% Paso 3: Revisión Administrativa
    rect rgb(255, 250, 240)
        Note over Admin, DB: 3: Revisión en Bandeja de Administración
        Admin->>UI: Accede a pedidos pendientes
        UI->>Backend: GET /pedidos?estado=PENDIENTE
        Backend->>DB: SELECT * FROM Pedidos WHERE estado = 'PENDIENTE'
        DB-->>Backend: Lista de solicitudes pendientes
        Backend-->>UI: Retorna pedidos
        UI-->>Admin: Muestra detalle: cátedra, requerimiento, vigencia y recursos
    end

    %% Paso 4: Aprobación y Despliegue Automático
    rect rgb(245, 255, 245)
        Note over Admin, Proxmox: 4: Aprobación y Despliegue en Servidores Locales
        Admin->>UI: Selecciona Template definitivo (y Opciones Avanzadas opcionales) y presiona "Aprobar"
        UI->>Backend: POST /pedidos/{id}/aprobar {templateId, configAvanzada}
        Backend->>DB: UPDATE Pedido SET estado = 'EN_DESPLIEGUE'
        Backend-->>UI: 200 Aprobación en proceso
        UI-->>Admin: Notifica inicio de aprovisionamiento

        Backend->>Proxmox: POST /nodes/{node}/lxc (o qemu) / clone<br/>(Template, RAM, CPU, Red VLAN/SDN)
        Proxmox->>Proxmox: Instancia contenedor/VM y arranca servicio
        Proxmox-->>Backend: Respuesta exitosa (vmid, IP asignada, estado: RUNNING)

        Backend->>DB: INSERT Servicio (pedido_id, vmid, ip, estado: "ACTIVO", vigencia)<br/>UPDATE Pedido SET estado = 'DISPONIBLE'
    end

    %% Paso 5 y 6: Notificación, Acceso y Autogestión
    rect rgb(248, 248, 255)
        Note over Catedra, Proxmox: 5 y 6: Visualización, Consumo y Autogestión
        Backend-->>UI: Notificación en tiempo real / Actualización de estado
        UI-->>Catedra: Notifica: "Tu recurso ya está disponible"
        
        Catedra->>UI: Ingresa a "Mis Servicios" y visualiza el recurso
        UI->>Backend: GET /servicios/{id}
        Backend->>DB: SELECT * FROM Servicios WHERE id = ...
        DB-->>Backend: Datos del servicio y credenciales/IP
        Backend-->>UI: Retorna estado ACTIVO, IP, URLs y vigencia
        UI-->>Catedra: Muestra accesos, métricas y botones (Reiniciar / Detener / Iniciar)

        opt Autogestión por la Cátedra
            Catedra->>UI: Click en "Reiniciar Servicio"
            UI->>Backend: POST /servicios/{id}/reboot
            Backend->>Proxmox: POST /nodes/{node}/lxc/{vmid}/status/reboot
            Proxmox-->>Backend: 200 OK
            Backend-->>UI: Servicio reiniciado exitosamente
            UI-->>Catedra: Confirmación en pantalla
        end
    end
```

---

## 5. Flujos Alternativos y Excepciones

### Flujo Alternativo 1: Rechazo con Motivo Escrito (FA-01)
- **Condición:** El Administrador evalúa que la solicitud no es factible técnicamente, no cuenta con justificación suficiente o la infraestructura no dispone de capacidad para el período solicitado.
- **Acción:** El Administrador presiona **Rechazar**, ingresando obligatoriamente un **motivo por escrito**.
- **Resultado:**
  - El Sistema actualiza el estado del pedido a `RECHAZADO`.
  - Se registra el motivo en la base de datos.
  - La Cátedra recibe una notificación con la explicación del rechazo y puede consultar el motivo en el detalle del pedido.

### Flujo Alternativo 2: Solicitud de Ajustes / Contrapropuesta por el Administrador (FA-02)
- **Condición:** El Administrador considera viable la solicitud pero requiere ajustar recursos (ej: reducir memoria de 16 GB a 8 GB o ajustar fechas de vigencia) debido a restricciones de hardware.
- **Acción:** El Administrador no aprueba de inmediato ni rechaza; solicita modificaciones detallando las sugerencias o cambios requeridos.
- **Resultado:**
  - El pedido pasa al estado `REQUIERE_AJUSTE` (devuelto a la cátedra).
  - La Cátedra es notificada y visualiza las observaciones del Administrador en su panel.
  - La Cátedra decide:
    - **Aceptar cambios sugeridos:** Actualiza el pedido según lo indicado y lo reenvía a revisión (pasa nuevamente a `PENDIENTE`).
    - **Desestimar solicitud:** Cancela el pedido voluntariamente.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Administrador
    participant UI as Portal NAP
    participant Backend as API Backend
    participant DB as Base de Datos
    actor Catedra as Usuario Cátedra

    Note over Admin, Catedra: Flujo Alternativo: Solicitud de Ajustes
    Admin->>UI: Revisa pedido y solicita modificaciones<br/>(ej: "Reducir a 8GB de RAM por capacidad")
    UI->>Backend: POST /pedidos/{id}/solicitar-ajuste {observaciones, recursosSugeridos}
    Backend->>DB: UPDATE Pedido SET estado = 'REQUIERE_AJUSTE', observaciones = ...
    DB-->>Backend: OK
    Backend-->>UI: Pedido devuelto para ajuste
    
    Backend-->>Catedra: Notificación: "Tu pedido requiere ajustes"
    Catedra->>UI: Abre pedido en estado REQUIERE_AJUSTE
    UI-->>Catedra: Muestra observaciones del Administrador

    alt Cátedra acepta y modifica
        Catedra->>UI: Ajusta especificaciones y confirma reenvío
        UI->>Backend: PUT /pedidos/{id} {recursosActualizados}
        Backend->>DB: UPDATE Pedido SET estado = 'PENDIENTE', recursos = ...
        Backend-->>UI: 200 Pedido reenviado
        UI-->>Catedra: Notificación: "Pedido reenviado a aprobación"
    else Cátedra cancela
        Catedra->>UI: Desiste del pedido y presiona "Cancelar"
        UI->>Backend: POST /pedidos/{id}/cancelar
        Backend->>DB: UPDATE Pedido SET estado = 'CANCELADO'
        UI-->>Catedra: Pedido cancelado
    end
```

---

## 6. Diagrama de Estados: Ciclo de Vida del Pedido y Servicio

```mermaid
stateDiagram-v2
    [*] --> PENDIENTE: Cátedra registra solicitud con vigencia
    
    PENDIENTE --> REQUIERE_AJUSTE: Admin solicita cambios de recursos/fechas
    REQUIERE_AJUSTE --> PENDIENTE: Cátedra ajusta y reenvía solicitud
    REQUIERE_AJUSTE --> CANCELADO: Cátedra desiste de la solicitud
    
    PENDIENTE --> RECHAZADO: Admin rechaza con motivo escrito
    
    PENDIENTE --> EN_DESPLIEGUE: Admin selecciona template y aprueba
    EN_DESPLIEGUE --> ERROR_DESPLIEGUE: Falla técnica en Proxmox VE
    ERROR_DESPLIEGUE --> EN_DESPLIEGUE: Admin reintenta aprovisionamiento
    
    EN_DESPLIEGUE --> DISPONIBLE: Orquestador finaliza con éxito
    
    DISPONIBLE --> SUSPENDIDO: Cátedra detiene servicio / Mantenimiento
    SUSPENDIDO --> DISPONIBLE: Cátedra inicia o reinicia servicio
    
    DISPONIBLE --> VENCIDO: Se cumple la fecha fin de vigencia
    VENCIDO --> DADO_DE_BAJA: Admin o sistema da de baja recursos
    
    RECHAZADO --> [*]
    CANCELADO --> [*]
    DADO_DE_BAJA --> [*]
```

---

## 7. Mapeo a Próximos Casos de Uso a Definir

Conforme a las respuestas del relevamiento técnico, se desprenden los siguientes casos de uso para completar la especificación:

1. **CU-02: Gestión y ABM de Templates de Recursos (Administrador):**
   - Alta, baja, modificación y catalogación de plantillas para IaaS (*Small*, *Medium*, *Large*), PaaS y SaaS.
2. **CU-03: Gestión de Ajustes, Observaciones y Rechazos de Pedidos:**
   - Flujo de interacción entre Admin y Cátedra con historial de comentarios y versionado de cambios.
3. **CU-04: Monitoreo y Autogestión de Servicios Activos (Cátedra):**
   - Acciones de ciclo de vida (Start, Stop, Reboot) y visualización de métricas de carga en Proxmox.
4. **CU-05: Control de Vigencia, Renovación y Desaprovisionamiento:**
   - Alertas por proximidad de vencimiento (cuatrimestre/año), solicitud de prórroga y baja controlada de recursos.

---

## 8. Estado de Implementación y Trazabilidad

| Componente | Estado | Referencia Técnica |
| :--- | :--- | :--- |
| **Modelos y Schemas** | Implementado & Verificado | `backend/app/models/pedido.py`, `backend/app/schemas/pedido.py`, `backend/app/schemas/template.py` |
| **API Endpoints** | Implementado & Verificado | `backend/app/routers/pedidos.py`, `backend/app/routers/servicios.py`, `backend/app/routers/templates.py` |
| **Aprovisionamiento Proxmox** | Implementado & Verificado | `backend/app/services/orquestacion_service.py` con opciones avanzadas |
| **Validación de Capacidad** | Implementado & Verificado | Límite constitucional de 8 GB (`backend/app/services/limites_service.py`) |
| **Frontend UI** | Implementado & Verificado | `Pedidos.jsx`, `Servicios.jsx`, `Templates.jsx`, `NuevoPedidoModal.jsx`, `AprobarPedidoModal.jsx`, `TemplatesAdmin.jsx` |
| **Pruebas Automatizadas** | 318/318 Tests Pasando | Suite completa con tests e2e en `backend/tests/test_quickstart_e2e.py` |

