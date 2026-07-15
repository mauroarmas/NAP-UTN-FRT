**Universidad Tecnológica Nacional**

**Facultad Regional Tucumán**

**PLAN DE TRABAJO DE PRÁCTICA SUPERVISADA**

**CARRERA DE INGENIERÍA EN SISTEMAS DE INFORMACIÓN**

**Diseño e Implementación de una Solución de Almacenamiento Distribuido y Políticas de Backup para una Nube Privada de la UTN FRT**

**NOMBRE DEL ESTUDIANTE:** [Nombre del estudiante]

**DOCENTE SUPERVISOR:**

**TUTOR DE PROYECTO:**

**CÁTEDRA:** Virtualización

**FECHA:** 16/06/2026

# Descripción General

El presente trabajo se desarrolla en el marco de un proyecto conjunto de la cátedra de Virtualización, orientado a diseñar e implementar una infraestructura de nube privada para la Universidad Tecnológica Nacional – Facultad Regional Tucumán (UTN FRT), que permita a las distintas cátedras de la institución alojar y administrar sus archivos y servicios de forma centralizada. El proyecto general es llevado a cabo por un equipo de tres estudiantes, dividiendo las tareas en dos grandes frentes complementarios: la infraestructura de virtualización (nodos físicos, clúster, redes y almacenamiento) y el desarrollo de un software de gestión y orquestación de los servicios por cátedra.

El presente plan de trabajo corresponde específicamente a la capa de almacenamiento del proyecto: el diseño e implementación de una solución de almacenamiento distribuido que permita desacoplar los discos virtuales de las máquinas virtuales del nodo físico en el que se ejecutan, de modo que la información de cada cátedra no dependa de un único nodo del clúster Proxmox VE. Esto es un requisito indispensable para que el mecanismo de alta disponibilidad del clúster (a cargo de otro integrante del equipo) pueda migrar o reiniciar automáticamente las máquinas virtuales en otro nodo ante una falla, sin pérdida de datos.

Para ello se evaluará e implementará una solución de almacenamiento compartido entre los nodos (como TrueNAS y/o Ceph, según los resultados del relevamiento técnico), junto con la definición de políticas de respaldo (backup) periódico de las máquinas virtuales y de los archivos alojados por cada cátedra, y procedimientos de recuperación ante fallos.

Como resultado de esta práctica se espera contar con un sistema de almacenamiento distribuido/compartido operativo e integrado al clúster Proxmox VE, políticas de backup configuradas y validadas, y la documentación técnica correspondiente a la arquitectura de almacenamiento y a los procedimientos de respaldo y recuperación.

# Objetivo general

* Diseñar e implementar una solución de almacenamiento distribuido/compartido para el clúster Proxmox VE de la infraestructura de nube privada de la UTN FRT, junto con políticas de backup y recuperación, que garantice la disponibilidad de la información de cada cátedra independientemente del nodo físico en el que se ejecuten sus servicios.

# Objetivos específicos

* Relevar los requerimientos de almacenamiento de las distintas cátedras (volumen estimado, tipo de archivos, criticidad de la información).
* Evaluar alternativas de almacenamiento compartido/distribuido compatibles con Proxmox VE (TrueNAS, Ceph, ZFS con replicación, entre otras) y seleccionar la más adecuada para los recursos disponibles.
* Diseñar la arquitectura de almacenamiento, definiendo su integración con la red de almacenamiento dedicada del clúster.
* Instalar y configurar la solución de almacenamiento seleccionada, e integrarla como storage compartido del clúster Proxmox VE.
* Configurar pools y/o datasets de almacenamiento independientes por cátedra, con sus respectivas cuotas.
* Definir e implementar políticas de backup periódico de las máquinas virtuales y de los archivos alojados, junto con procedimientos de recuperación ante fallos.
* Documentar la arquitectura de almacenamiento implementada y los procedimientos de administración, backup y recuperación.

# Metodología de Desarrollo

La metodología adoptada para esta práctica supervisada se basa en un enfoque incremental, partiendo del relevamiento de los requerimientos de almacenamiento, avanzando hacia la evaluación y selección de la tecnología de almacenamiento distribuido, su instalación e integración con el clúster Proxmox VE, y finalizando con la configuración de políticas de backup y la documentación del trabajo realizado. Las tareas se coordinan permanentemente con el compañero responsable del clúster de cómputo y redes, dado que la solución de almacenamiento depende directamente de la red dedicada y de la configuración de alta disponibilidad allí definida, y con el compañero responsable del software de gestión, en lo referido a cuotas y aislamiento de almacenamiento por cátedra.

## 1. Investigación y relevamiento

* Relevamiento de los requerimientos de almacenamiento estimados por cátedra (volumen, tipo de archivos, frecuencia de acceso).
* Relevamiento de la capacidad de disco disponible en cada uno de los cinco nodos físicos del clúster.
* Investigación comparativa de soluciones de almacenamiento distribuido compatibles con Proxmox VE: TrueNAS (NFS/iSCSI), Ceph (almacenamiento hiperconvergente) y ZFS con replicación.
* Revisión de la documentación oficial de las tecnologías evaluadas y de casos de uso similares en entornos académicos.

## 2. Diseño de la arquitectura de almacenamiento

* Selección justificada de la tecnología de almacenamiento a implementar, en función de los recursos disponibles y los requerimientos relevados.
* Diseño de la integración de la solución de almacenamiento con la red dedicada de almacenamiento del clúster.
* Definición de la estructura de pools, datasets o volúmenes a crear, con un espacio independiente por cátedra.
* Planificación de la estrategia de backup: frecuencia, retención y destino de las copias de respaldo.

## 3. Implementación del almacenamiento distribuido

* Instalación y configuración de la solución de almacenamiento seleccionada (TrueNAS y/o Ceph) sobre la infraestructura disponible.
* Integración del almacenamiento como storage compartido dentro del clúster Proxmox VE.
* Configuración de los pools/datasets independientes por cátedra y de sus cuotas correspondientes.
* Pruebas iniciales de lectura/escritura y de rendimiento sobre el almacenamiento configurado.

## 4. Integración con alta disponibilidad y migración de máquinas virtuales

* Validación de que los discos virtuales de las máquinas virtuales residen en el almacenamiento compartido y no en el almacenamiento local de cada nodo.
* Pruebas de migración en caliente de máquinas virtuales entre nodos, verificando la continuidad del acceso a los datos.
* Pruebas de simulación de caída de un nodo, validando que el almacenamiento permanece accesible desde los nodos restantes.
* Ajustes de configuración en conjunto con el compañero responsable del clúster de cómputo, en función de los resultados obtenidos.

## 5. Configuración de backups y recuperación

* Configuración de tareas de backup periódico de las máquinas virtuales mediante las herramientas nativas de Proxmox VE (vzdump) y/o de la solución de almacenamiento elegida.
* Configuración de backup de los archivos alojados por cada cátedra, incluyendo política de retención de versiones.
* Pruebas de restauración de backups, tanto de máquinas virtuales completas como de archivos individuales.
* Documentación de los procedimientos de backup y de recuperación ante distintos escenarios de fallo.

## 6. Documentación y presentación final

* Redacción del informe técnico final detallando la arquitectura de almacenamiento implementada y su integración con el clúster.
* Elaboración de diagramas de la arquitectura de almacenamiento y de los flujos de backup y recuperación.
* Documentación de los procedimientos de administración, monitoreo y mantenimiento del almacenamiento.
* Recomendaciones para la futura escalabilidad del almacenamiento ante el crecimiento de las cátedras o del volumen de datos.

# Cronograma

| **Semana** | **Actividad** | **Duración (Horas)** |
| --- | --- | --- |
| 1 | Investigación y relevamiento de requerimientos de almacenamiento | 25 |
| 2 | Evaluación de tecnologías y diseño de la arquitectura de almacenamiento | 30 |
| 3 | Instalación y configuración de la solución de almacenamiento distribuido | 40 |
| 4 |  |  |
| 5 | Integración con el clúster Proxmox VE y configuración de pools por cátedra | 35 |
| 6 | Integración con alta disponibilidad y pruebas de migración | 30 |
| 7 | Configuración de políticas de backup y recuperación | 30 |
| 8 |  |  |
| 9 | Pruebas integrales con el equipo (cómputo y software de gestión) | 20 |
| 10 | Documentación y presentación final | 25 |
| **Total** |  | **235** |

# Referencias Bibliográficas

[1] Proxmox Server Solutions GmbH. (2024). Proxmox VE Storage Documentation. Disponible en https://pve.proxmox.com/pve-docs/

[2] iXsystems. (2024). TrueNAS Documentation Hub. Disponible en https://www.truenas.com/docs/

[3] Ceph Foundation. (2024). Ceph Documentation. Disponible en https://docs.ceph.com/

[4] Marshall, D. (2021). Mastering Proxmox (4th ed.). Packt Publishing.

[5] Lutkevich, B., & Beal, V. (2022). Storage area network (SAN) vs. network attached storage (NAS). TechTarget.

[6] NIST. (2011). The NIST Definition of Cloud Computing (SP 800-145). National Institute of Standards and Technology.

[7] Proxmox Server Solutions GmbH. (2024). Backup and Restore — Proxmox VE Documentation. Disponible en https://pve.proxmox.com/wiki/Backup\_and\_Restore
