**Universidad Tecnológica Nacional**

**Facultad Regional Tucumán**

**PLAN DE TRABAJO DE PRÁCTICA SUPERVISADA**

**CARRERA DE INGENIERÍA EN SISTEMAS DE INFORMACIÓN**

**Desarrollo de un Software de Gestión y Orquestación de Servicios por Cátedra para una Nube Privada de la UTN FRT**

**NOMBRE DEL ESTUDIANTE:** [Nombre del estudiante]

**DOCENTE SUPERVISOR:**

**TUTOR DE PROYECTO:**

**CÁTEDRA:** Virtualización

**FECHA:** 16/06/2026

# Descripción General

El presente trabajo se desarrolla en el marco de un proyecto conjunto de la cátedra de Virtualización, orientado a diseñar e implementar una infraestructura de nube privada para la Universidad Tecnológica Nacional – Facultad Regional Tucumán (UTN FRT), que permita a las distintas cátedras de la institución alojar y administrar sus servicios de forma centralizada. El proyecto general es llevado a cabo por un equipo de tres estudiantes, con responsabilidades diferenciadas: la infraestructura de virtualización (configuración del clúster Proxmox VE de cinco nodos y dispositivos de networking Mikrotik), el almacenamiento distribuido (TrueNAS) y el desarrollo del software de gestión y orquestación, que es el objeto de esta práctica supervisada.

El presente plan de trabajo corresponde específicamente al desarrollo del software de gestión: un portal web que actúa como intermediario (middleware) entre los usuarios finales —responsables de cátedra— y la infraestructura subyacente. El propósito es que los usuarios no interactúen directamente con Proxmox VE ni con ningún componente de la infraestructura, sino que utilicen exclusivamente este software como punto de contacto para la solicitud, seguimiento y administración de sus servicios. El software se integrará, mediante APIs, con el clúster Proxmox VE, y deberá permitir definir entornos independientes por cátedra con cuotas de recursos de cómputo (CPU y RAM) y almacenamiento, ofrecer observabilidad de los recursos y servicios en uso, y posibilitar el despliegue simplificado de servicios bajo un modelo PaaS/SaaS.

El sistema contará con un mecanismo propio de autenticación y gestión de roles, de modo que cada cátedra acceda a su espacio de administración, mientras que un administrador general supervise y gestione los recursos globales de la plataforma. Se implementará un flujo de gestión de pedidos de servicios que permita a las cátedras solicitar recursos (contenedores, máquinas virtuales o software específico) y realizar el seguimiento del estado de su pedido hasta su efectivización, tomando como referencia los modelos de aprovisionamiento de los proveedores de nube pública. Asimismo, se definirá un catálogo de templates de recursos estandarizados, adaptados a las capacidades reales de la infraestructura disponible.

El software se desplegará como un componente independiente dentro de la plataforma (en un contenedor dedicado) y se evaluará la posibilidad de integrar, además de la gestión de Proxmox VE, la administración de los dispositivos de red Mikrotik y la integración del acceso con el correo electrónico institucional de la facultad.

Como resultado de esta práctica se espera contar con un software de gestión funcional, con su portal web correspondiente, integrado con el clúster Proxmox VE mediante APIs, capaz de gestionar pedidos de servicios con seguimiento de estados, definir entornos por cátedra con cuotas de recursos, ofrecer observabilidad básica de los servicios desplegados y permitir el despliegue simplificado de servicios, junto con la documentación técnica y el manual de uso correspondientes.

# Objetivo general

- Diseñar e implementar un software de gestión y orquestación que, actuando como intermediario entre los usuarios y la infraestructura, permita a las cátedras de la UTN FRT solicitar, administrar y monitorear servicios de cómputo y almacenamiento a través de un portal web con gestión de pedidos, seguimiento de estados y observabilidad, sin interacción directa con Proxmox VE ni con los componentes de infraestructura subyacentes.

# Objetivos específicos

- Relevar los requerimientos funcionales del software de gestión en función de las necesidades de administración de cada cátedra y de los lineamientos establecidos por el docente supervisor.
- Diseñar la arquitectura del software como middleware, incluyendo su integración con la API de Proxmox VE, su modelo de despliegue dentro de la plataforma y la interfaz de usuario del portal web.
- Definir el modelo de entornos por cátedra, incluyendo la asignación de cuotas de recursos de CPU, RAM y almacenamiento, y un catálogo de templates de recursos estandarizados.
- Implementar un sistema de autenticación y autorización propio del software, con gestión de roles diferenciados (administrador general, responsable de cátedra).
- Desarrollar un módulo de gestión de pedidos de servicios con flujo de transición de estados, que permita a las cátedras solicitar recursos y realizar el seguimiento de sus pedidos hasta su efectivización.
- Implementar los mecanismos de comunicación con la API de Proxmox VE para la creación, configuración, monitoreo y eliminación de máquinas virtuales y contenedores.
- Desarrollar las funcionalidades de observabilidad básica: monitoreo de uso de recursos y estado de los servicios desplegados por cátedra.
- Desarrollar el portal web (interfaz de usuario) orientado tanto a los responsables de cátedra como al administrador general de la plataforma.
- Evaluar e implementar, de ser viable, la integración con los dispositivos de red Mikrotik y la autenticación mediante el correo electrónico institucional de la facultad.
- Documentar la arquitectura del software desarrollado y elaborar manuales de uso orientados a los responsables de cátedra y al administrador de la plataforma.

# Metodología de Desarrollo

La metodología adoptada para esta práctica supervisada se basa en un enfoque incremental e iterativo, partiendo del relevamiento de los requerimientos funcionales del software —enriquecido con entrevistas al docente supervisor—, avanzando hacia el diseño de su arquitectura, el desarrollo progresivo de los módulos de backend y frontend, y finalizando con la validación integral junto con el resto del equipo y la documentación del trabajo realizado. Se busca obtener un prototipo funcional base en las primeras etapas, sobre el cual se iterará incorporando funcionalidades adicionales. Las tareas se coordinan permanentemente con los compañeros responsables del clúster de cómputo y del almacenamiento distribuido, dado que el software depende de los pools de recursos y de la disponibilidad de la infraestructura definidos por ellos.

Se prevé como principal dificultad la dependencia con la disponibilidad de la infraestructura física (nodos, red, almacenamiento) para las pruebas de integración, lo cual se mitigará mediante el desarrollo y las pruebas unitarias en entornos locales o simulados hasta que la infraestructura esté operativa.

## 1. Investigación y relevamiento

- Relevamiento de los requerimientos funcionales del software de gestión mediante entrevistas con el docente supervisor y análisis de las necesidades de administración por cátedra.
- Revisión de la documentación oficial de la API de Proxmox VE para la gestión de máquinas virtuales, contenedores y recursos.
- Análisis de interfaces de administración de nubes públicas (AWS, Google Cloud) como referencia para el diseño de la experiencia de usuario y el flujo de gestión de pedidos.
- Investigación de herramientas y bibliotecas existentes para la integración programática con Proxmox VE y con dispositivos de red Mikrotik.
- Relevamiento de los recursos totales disponibles en el clúster (CPU, RAM, almacenamiento) para definir los criterios de asignación por cátedra y los templates de recursos.

## 2. Diseño de la arquitectura del software

- Definición de la arquitectura general del software: backend de orquestación (API), frontend (portal web) y base de datos.
- Diseño del modelo de entornos por cátedra, incluyendo la definición de cuotas de recursos (CPU, RAM, almacenamiento), su aislamiento lógico y el catálogo de templates estandarizados.
- Diseño del flujo de gestión de pedidos de servicios, incluyendo los estados por los que transita cada solicitud.
- Diseño del modelo de autenticación, autorización y roles del sistema.
- Definición del modelo de despliegue del propio software dentro de la plataforma (contenedor dedicado).
- Diseño preliminar de las interfaces de usuario del portal, tanto para el responsable de cátedra como para el administrador general.

## 3. Desarrollo del backend y núcleo de orquestación

- Implementación del sistema de autenticación y autorización con gestión de roles (administrador general, responsable de cátedra).
- Desarrollo del módulo de gestión de cátedras, con creación de espacios aislados y asignación de cuotas de recursos.
- Implementación de la integración con la API de Proxmox VE para la creación, configuración, monitoreo y eliminación de máquinas virtuales y contenedores.
- Desarrollo del módulo de gestión de pedidos de servicios con flujo de transición de estados y notificaciones.
- Implementación del catálogo de templates de recursos.
- Pruebas unitarias y de integración del backend.

## 4. Desarrollo del frontend (portal web)

- Desarrollo de las pantallas de autenticación y gestión de sesión.
- Desarrollo del dashboard del responsable de cátedra: visualización de servicios activos, solicitud de nuevos servicios, seguimiento del estado de pedidos y métricas de consumo.
- Desarrollo del panel de administración: gestión global de recursos, aprobación de pedidos, administración de usuarios y cátedras, y configuración de templates y cuotas.
- Integración del frontend con la API del backend.

## 5. Observabilidad, monitoreo e integraciones

- Implementación del módulo de monitoreo de recursos (uso de CPU, RAM y almacenamiento) por cátedra y por servicio desplegado.
- Desarrollo de las visualizaciones de monitoreo en el panel de administración y en el dashboard de cátedra.
- Implementación de alertas o notificaciones básicas ante consumo excesivo de recursos o caída de servicios.
- Evaluación e implementación, si resulta viable dentro del alcance, de la integración con dispositivos Mikrotik para la administración básica de la red desde el portal.

## 6. Pruebas integrales y ajustes

- Pruebas integrales del software en conjunto con el clúster Proxmox VE y el almacenamiento TrueNAS implementados por los compañeros del equipo.
- Pruebas del flujo completo de solicitud de servicio: desde el pedido por parte de una cátedra hasta el despliegue efectivo y su monitoreo.
- Pruebas de despliegue de servicios de prueba para validar el modelo PaaS/SaaS de extremo a extremo.
- Ajustes de la plataforma en función de los resultados obtenidos y del feedback de uso simulado por parte de una cátedra de prueba.
- Corrección de errores y optimización de los módulos desarrollados.

## 7. Documentación y presentación final

- Redacción del informe técnico final detallando el diseño y desarrollo del software de gestión.
- Elaboración de un manual de uso orientado a los responsables de cada cátedra para la solicitud y administración de sus servicios.
- Elaboración de un manual de administración orientado al administrador general de la plataforma.
- Documentación de la arquitectura del software, su integración con la API de Proxmox VE y los procedimientos de mantenimiento y despliegue.
- Recomendaciones para la futura incorporación de nuevos servicios, integración con autenticación institucional y escalabilidad de la plataforma.

# Cronograma

| **Semana** | **Actividad** | **Duración (Horas)** |
| --- | --- | --- |
| 1 | Investigación y relevamiento de requerimientos funcionales | 20 |
| 2 | Diseño de la arquitectura del software, modelo de datos y flujo de pedidos | 25 |
| 3-4 | Desarrollo del backend: autenticación, roles e integración con Proxmox VE | 45 |
| 5-6 | Desarrollo del frontend: portal de cátedra y panel de administración | 40 |
| 7 | Implementación del modelo PaaS/SaaS y despliegue automatizado de servicios | 20 |
| 8 | Observabilidad, monitoreo de recursos e integraciones complementarias | 15 |
| 9 | Pruebas integrales con el equipo y ajustes | 35 |
| 10 | Documentación y presentación final | 35 |
| **Total** | | **235** |

# Referencias Bibliográficas

[1] Proxmox Server Solutions GmbH. (2024). Proxmox VE API Documentation. Disponible en https://pve.proxmox.com/pve-docs/api-viewer/

[2] Richardson, C. (2018). Microservices Patterns. Manning Publications.

[3] Newman, S. (2021). Building Microservices (2nd ed.). O'Reilly Media.

[4] NIST. (2011). The NIST Definition of Cloud Computing (SP 800-145). National Institute of Standards and Technology.

[5] Mell, P., & Grance, T. (2011). Cloud Computing Synopsis and Recommendations (SP 800-146). NIST.

[6] Burns, B. (2018). Designing Distributed Systems. O'Reilly Media.

[7] Fielding, R. T. (2000). Architectural Styles and the Design of Network-based Software Architectures (Tesis doctoral). University of California, Irvine.
