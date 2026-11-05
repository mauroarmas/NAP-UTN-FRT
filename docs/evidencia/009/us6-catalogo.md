# US6 — Catálogo y perfiles: avance local

Verificado el 2026-10-20 (zona institucional). Esto acredita catálogo/perfiles con dobles y PostgreSQL aislado; no acredita imágenes construidas, runner instalado ni entrega real.

- Definiciones de Linux, PostgreSQL y BookStack con estados borrador/validada/publicada/retirada. Manifiesto cerrado Draft 2020-12 y formatos, identidad/versiones, componentes y paquetes coherentes; borradores parciales no se publican. Contenido validado inmutable y retiro auditado.
- Validación vinculada al documento previamente importado: UUID, checksum, imagen/receta, dos instancias distintas, checks, clúster y fecha coincidentes. La configuración de infraestructura identifica archivos de imagen/bundle cuyo hash se comprueba y su presencia en PVE; rutas o comandos recibidos del solicitante no se ejecutan.
- Perfiles nuevos requieren definición publicada compatible, mínimos e imagen correcta. No se admiten nuevas ofertas QEMU ni recursos desligados de una definición. La migración aditiva `009_09_perfiles_definicion` deja nulas las referencias históricas desconocidas.
- Altas/reenvíos verifican la oferta actual; evaluación exige la definición exacta del perfil. Aprobar conserva versión y hash. Retirar impide solicitudes nuevas y no altera el snapshot ni impide admitir el despliegue de una aprobación anterior. La preparación real sigue bloqueada hasta completar US6.
- Las lecturas docentes omiten imagen/configuración PVE y filtran ofertas no disponibles. Las referencias históricas ajenas no se exponen; las propias siguen legibles. Las renovaciones históricas conservan su producto.
- PostgreSQL verifica la carrera de aprobación/retiro y casos representativos de doble aprobación, inicio y renovaciones, además de migración desde vacío/legacy. Las decisiones concurrentes conservan un compromiso único y ninguna aceptación de una versión retirada antes de la decisión.

| Verificación | Resultado | Log local |
|---|---|---|
| Catálogo/perfiles y regresiones de evaluación, calendario, proyecciones y payloads | 30 aprobadas, 17,28 s | `/tmp/nap009-us6-profiles-verified.txt` |
| Migraciones, retiro/aprobación, capacidad y renovación en PostgreSQL 16 | 12 aprobadas, 19,96 s | `/tmp/nap009-us6-profiles-postgres.txt` |
| Schemas empaquetados y ejemplos | 2 schemas y 13 ejemplos válidos | `backend/scripts/validar_contratos.py` |
| Recolección explícita infra | 12 casos, ambas suites presentes | `/tmp/nap009-us6-infra-collection.txt` |

Las pruebas de runner/cliente/acceso se escribieron antes de las interfaces y permanecen pendientes de pasar. La nueva prueba de UI de acceso todavía importa un componente inexistente; por eso no se declara aprobada la suite frontend completa durante esta etapa. Los resultados previos de US5 conservan su alcance.

Las plantillas de capacidad de pruebas ahora usan una definición/evidencia sintéticas explícitas. No se añadió una excepción operativa para omitir la validación de ofertas. No se migró una base operativa, no se arrancó el worker contra PVE real y no se publicaron artefactos reales.
