# Carga inicial y comprobaciones de interfaz

La SPA se compiló con el lock de npm del proyecto y Node 24. Se comparan los archivos JavaScript realmente requeridos por la entrada, recorriendo los imports estáticos del manifest de Vite. Las gráficas y rutas diferidas quedan fuera de esa entrada; el total incluye también los chunks diferidos. gzip usa mtime=0 y se calcula por archivo.

| Medida | Antes | Después |
|---|---:|---:|
| JavaScript inicial, bytes | 800238 | 316330 |
| JavaScript inicial gzip, bytes | 236280 | 102446 |
| JavaScript total, bytes | 800238 | 808624 |
| Chunks JavaScript | 1 | 23 |

Reducción inicial: 60,5 % sin comprimir y 56,6 % con gzip. El total aumenta ligeramente por la separación de módulos. Las cifras describen el bundle, no el tiempo de respuesta de SC-008.

Se mantienen Login/Seguridad disponibles durante la habilitación. Cada ruta tiene límite de error recuperable; las gráficas se solicitan al abrir el historial. Las consultas usan cancelación, clave de alcance y conservación explícita de la última respuesta confirmada. Los GET de lectura no capturan métricas en PVE. La tabla y el resumen textual conservan los bytes exactos aunque excedan la precisión de Number.

Validación: 37 pruebas Vitest aprobadas (14,08 s); tres recorridos Playwright sobre SPA compilada aprobados (14,9 s): carga diferida de gráficas, historial/tabla y error de refresco; formularios con Enter sin doble envío; error de chunk con navegación recuperable. Los dos recorridos de teclado aprobaron (11,3 s), incluyendo foco, fondo inerte y retorno. API sustituida y red externa bloqueada en estas pruebas funcionales. Capturas de escritorio y móvil inspeccionadas localmente; se corrigió el ajuste del texto y los ejes. Lint sin errores, con advertencias heredadas.

**SC-008:** el ensayo posterior con PostgreSQL/12,96M muestras y diez contextos aprobó; ver [protocolo y resultados](rendimiento-laboratorio.md). El bundle y las pruebas funcionales por sí solos no acreditan ese umbral. La validación con el responsable de una cátedra sigue pendiente.
