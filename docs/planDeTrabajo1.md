**Universidad Tecnológica Nacional**

**Facultad Regional Tucumán**

**PLAN DE TRABAJO DE PRÁCTICA SUPERVISADA**

**CARRERA DE INGENIERÍA EN SISTEMAS DE INFORMACIÓN**

**Diseño e Implementación de un Clúster de Virtualización Proxmox VE con Alta Disponibilidad para una Nube Privada de la UTN FRT**

**NOMBRE DEL ESTUDIANTE:** Ochoa, Alejandro Iván

**DOCENTE SUPERVISOR:**

**TUTOR DE PROYECTO:**

**CÁTEDRA:** Virtualización

**FECHA:** 16/06/2026

# Descripción General

El presente trabajo se desarrolla en el marco de un proyecto conjunto de la cátedra de Virtualización, orientado a diseñar e implementar una infraestructura de nube privada para la Universidad Tecnológica Nacional – Facultad Regional Tucumán (UTN FRT), que permita a las distintas cátedras de la institución alojar y administrar sus archivos y servicios de forma centralizada. El proyecto general es llevado a cabo por un equipo de tres estudiantes, dividiendo las tareas en dos grandes frentes complementarios: la infraestructura de virtualización (nodos físicos, clúster, redes y almacenamiento) y el desarrollo de un software de gestión y orquestación de los servicios por cátedra.

El presente plan de trabajo corresponde específicamente a la parte de infraestructura de cómputo y redes del proyecto: el diseño, instalación y configuración de un clúster de cinco nodos físicos bajo el hipervisor Proxmox VE, con el objetivo de lograr alta disponibilidad (HA) entre los nodos, segmentación de redes para separar el tráfico de almacenamiento del tráfico de cómputo/Internet, y la base de cómputo sobre la cual se desplegarán las máquinas virtuales y contenedores de cada cátedra.

Actualmente se dispone de cinco equipos físicos con recursos limitados (aproximadamente 8 GB de RAM y 2 TB de disco por nodo), por lo que la solución se plantea como un prototipo funcional que demuestre el comportamiento del clúster, su mecanismo de alta disponibilidad y su capacidad de servir como base de cómputo para una plataforma de nube privada, sentando las bases para una futura migración a hardware de mayor capacidad.

Como resultado de esta práctica se espera contar con un clúster Proxmox VE de cinco nodos operativo, con redes segregadas (red de almacenamiento y red de cómputo/acceso), mecanismos de alta disponibilidad configurados y validados, y la documentación técnica correspondiente a la arquitectura de cómputo y redes del proyecto.

# Objetivo general

* Diseñar e implementar un clúster de virtualización Proxmox VE de cinco nodos, con segmentación de redes y mecanismos de alta disponibilidad, que constituya la capa de cómputo de la infraestructura de nube privada de la UTN FRT, documentando la arquitectura y los procedimientos de configuración correspondientes.

# Objetivos específicos

* Relevar las características de los equipos físicos disponibles (CPU, memoria, almacenamiento, placas de red) y las restricciones de infraestructura existentes.
* Diseñar la arquitectura del clúster Proxmox VE, definiendo la cantidad de nodos, su rol y la segmentación de redes necesaria.
* Configurar una red dedicada para el tráfico de almacenamiento (storage network) y una red separada para el tráfico de cómputo y acceso desde Internet.
* Instalar y configurar Proxmox VE en los cinco nodos físicos, integrándolos en un único clúster administrado de forma centralizada.
* Configurar los mecanismos de alta disponibilidad (HA) del clúster, de modo que ante la caída de un nodo las máquinas virtuales puedan migrarse o reiniciarse automáticamente en otro nodo disponible.
* Validar el funcionamiento del clúster mediante pruebas de migración de máquinas virtuales y simulación de fallos de nodo.
* Documentar la arquitectura de cómputo y redes implementada, incluyendo diagramas de red, configuración del clúster y procedimientos de administración.

# Metodología de Desarrollo

La metodología adoptada para esta práctica supervisada se basa en un enfoque incremental, partiendo del relevamiento de los recursos físicos disponibles, avanzando hacia el diseño de la arquitectura de red y cómputo, la instalación y configuración del clúster Proxmox VE, y finalizando con la validación de los mecanismos de alta disponibilidad y la documentación del trabajo realizado. Las tareas se coordinan permanentemente con los compañeros responsables del almacenamiento distribuido y del software de gestión, dado que ambos componentes dependen directamente del clúster de cómputo aquí descripto.

## 1. Investigación y relevamiento

* Relevamiento de las características técnicas de los cinco equipos físicos disponibles (memoria RAM, capacidad de disco, placas de red, año y estado de los equipos).
* Identificación de las placas de red disponibles en cada nodo y su asignación funcional (red de almacenamiento y red de cómputo).
* Relevamiento de los requerimientos de cómputo estimados por cátedra, en coordinación con el resto del equipo.
* Revisión de la documentación oficial de Proxmox VE y de buenas prácticas de clusterización y alta disponibilidad.

## 2. Diseño de la arquitectura de cómputo y redes

* Definición de la topología del clúster: cinco nodos físicos Proxmox VE interconectados.
* Diseño de la segmentación de redes: una red dedicada al tráfico de almacenamiento (comunicación entre nodos y el sistema de almacenamiento distribuido) y otra red para el tráfico de cómputo y acceso de los servicios hacia Internet.
* Definición de los recursos de cómputo (CPU, RAM) que se reservarán como pool de recursos por cátedra, en coordinación con el encargado del software de gestión.
* Planificación de la estrategia de alta disponibilidad: políticas de migración y reinicio automático de máquinas virtuales ante fallos de nodo.

## 3. Instalación y configuración de los nodos Proxmox VE

* Instalación de Proxmox VE en cada uno de los cinco nodos físicos.
* Configuración de la interfaz de red de cómputo/acceso y de la interfaz de red de almacenamiento en cada nodo.
* Unificación de los cinco nodos en un único clúster Proxmox administrado de forma centralizada.
* Configuración de la autenticación, certificados y políticas básicas de seguridad del clúster.

## 4. Configuración de alta disponibilidad (HA)

* Configuración de los grupos de alta disponibilidad (HA groups) y de las políticas de prioridad entre nodos.
* Integración del clúster con el sistema de almacenamiento compartido/distribuido (coordinado con el compañero responsable de storage) como requisito para la migración en caliente de máquinas virtuales.
* Configuración de las políticas de reinicio y migración automática de máquinas virtuales ante la caída de un nodo (fencing y watchdog).
* Documentación de los parámetros de configuración de HA aplicados al clúster.

## 5. Pruebas de validación del clúster

* Pruebas de migración en caliente (live migration) de máquinas virtuales entre nodos.
* Simulación de fallos de nodo (apagado forzado) para validar el comportamiento de la alta disponibilidad.
* Pruebas de carga básica sobre el clúster para verificar la correcta distribución de recursos entre cátedras.
* Pruebas integrales en conjunto con los compañeros responsables del almacenamiento distribuido y del software de gestión.

## 6. Documentación y presentación final

* Redacción del informe técnico final detallando el diseño de la arquitectura de cómputo y redes, y el proceso de implementación del clúster.
* Elaboración de diagramas de red y de la topología final del clúster Proxmox VE.
* Documentación de los procedimientos de administración, mantenimiento y recuperación ante fallos del clúster.
* Recomendaciones para la futura escalabilidad del clúster ante la incorporación de hardware adicional.

# Cronograma

| **Semana** | **Actividad** | **Duración (Horas)** |
| --- | --- | --- |
| 1 | Investigación y relevamiento de equipos y requerimientos | 25 |
| 2 | Diseño de la arquitectura de cómputo y segmentación de redes | 25 |
| 3 | Instalación y configuración de Proxmox VE en los nodos | 40 |
| 4 |  |  |
| 5 | Unificación del clúster y configuración de red de almacenamiento/cómputo | 35 |
| 6 | Configuración de alta disponibilidad (HA) | 40 |
| 7 |  |  |
| 8 | Pruebas de validación (migración, fallos de nodo, carga) | 30 |
| 9 | Pruebas integrales con el equipo (storage y software de gestión) | 20 |
| 10 | Documentación y presentación final | 20 |
| **Total** |  | **235** |

# Referencias Bibliográficas

[1] Proxmox Server Solutions GmbH. (2024). Proxmox VE Administration Guide. Disponible en https://pve.proxmox.com/pve-docs/

[2] Marshall, D. (2021). Mastering Proxmox (4th ed.). Packt Publishing.

[3] Portnoy, M. (2012). Virtualization Essentials. Wiley.

[4] Kurose, J. F., & Ross, K. W. (2021). Computer Networking: A Top-Down Approach (8th ed.). Pearson.

[5] Stallings, W. (2018). Operating Systems: Internals and Design Principles (9th ed.). Pearson.

[6] NIST. (2011). The NIST Definition of Cloud Computing (SP 800-145). National Institute of Standards and Technology.

[7] Proxmox Server Solutions GmbH. (2024). High Availability Cluster — Proxmox VE Documentation. Disponible en https://pve.proxmox.com/wiki/High\_Availability
