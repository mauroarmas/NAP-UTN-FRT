# Documentación de NAP

## Para trabajar ahora

- [Traspaso de la implementación 011](traspaso-011.md): estado, entorno, datos y siguiente paso.
- [Prompt de continuación para Claude](prompt-continuacion-011.md).
- [Alcance reducido: Docker Hub e imágenes propias](../specs/011-desplegar-servicios-universitarios/cambio-alcance-oci.md).
- [Spec 011 y tareas](../specs/011-desplegar-servicios-universitarios/tasks.md).
- [Rumbo del producto](rumbo-mini-cloud.md) y [constitución](../.specify/memory/constitution.md).

## Uso e instalación

- [Manual docente](manual-docente.md), [manual administrador](manual-administrador.md).
- [Servicios](administracion-servicios.md) y [acceso a aplicaciones](acceso-aplicaciones-nap.md).
- [Docker](../DOCKER.md), [conexión a infraestructura](conexion-infraestructura.md).
- [Respaldos](operacion-respaldos.md) y [restauración operativa](preparar-restauracion.md).
- [Laboratorio de Mauro](laboratorio-biblioteca.md): referencias a archivos privados
  de su equipo, no instrucciones directamente portables.

## Evidencia y antecedentes

`evidencia/009`, `evidencia/010` y `evidencia/011` son bitácoras fechadas. Una prueba
antigua aprobada no habilita automáticamente el runtime nuevo. Para 011 leer
[base común](evidencia/011/base-comun.md), [imágenes propias](evidencia/011/us1-imagenes.md)
y [compuertas de factibilidad](evidencia/011/compuertas.md).

`analisis-proyecto-2026-10-18.md`, `implementation_plan.md`, `planDeTrabajo2.md`,
los planes de la raíz y las specs anteriores son antecedentes: no usar sus
instrucciones antiguas de cuentas, despliegue o publicación como procedimiento
actual. Se conservan porque explican decisiones, requisitos académicos y enlaces
desde las specs. `nuevaDoc/` y `paper.md` son material académico.

Limpieza del 27/10: se retiraron el script que restablecía cuentas con contraseñas
fijas, seis funciones/alias de API del frontend sin consumidores y el texto base
de Vite. Se agregó este índice para separar documentos vigentes de antecedentes.
Las migraciones, pruebas, evidencias y endpoints históricos se conservan: parte
del legado sigue dando servicio a Draw.io/IaaS y al historial de pedidos.
