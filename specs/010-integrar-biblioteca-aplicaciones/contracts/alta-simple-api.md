# Alta simple de aplicaciones — contrato vigente

Ajuste autorizado por el usuario el 25/10/2026. Sustituye los campos técnicos y el TTL de la interfaz administrativa de US2. Los contratos técnicos anteriores continúan disponibles para compatibilidad; no forman parte del recorrido normal del portal.

## Recorrido

**Elegir aplicación → Preparar → Abrir y comprobar → Publicar o eliminar.**

Administración sólo completa nombre, descripción opcional y tamaño Small/Medium. NAP resuelve perfil institucional, revisión, entradas fijadas, construcción, distribución y registro. No solicita entorno, plazo, hashes, versión ni documento JSON. El estado se recupera al volver a abrir la ventana.

La preparación nueva no tiene expiración ni aviso por TTL. Publicar conserva el artefacto y la oferta y limpia los recursos auxiliares. Eliminar conserva auditoría y limpia recursos; la capacidad sólo se libera con ausencia confirmada. No se altera la vigencia de pedidos académicos.

## API

Prefijo `/api/v1/biblioteca/incorporaciones/{id}`. Todas las rutas requieren administrador vigente. Mutaciones usan sesión/CSRF e `Idempotency-Key`; GET lleva `Cache-Control: no-store`.

| Método y sufijo | Entrada | Efecto |
|---|---|---|
| GET `/preparacion` | — | Estado y acciones disponibles, datos de formulario recuperables y referencias de acceso sin secretos |
| POST `/preparar` | `nombre`, `descripcion`, `tamano` | Inicia o recupera una preparación; selección técnica automática |
| POST `/confirmar-funcionamiento` | `funciona: true/false` | Confirma funcionamiento o solicita eliminación |
| POST `/publicar` | `nombre`, `descripcion`, `tamano` | Valida y publica la oferta comprobada |
| POST `/eliminar` | `{}` | Cancela y elimina recursos de preparación de forma duradera |

`tamano` admite `small` o `medium`. Nombre máximo 100 caracteres; descripción opcional máximo 2000. El backend rechaza nombres duplicados, tamaños insuficientes y publicación antes de completar la preparación y comprobación. Un doble clic no crea dos preparaciones. Sin configuración institucional se informa el impedimento antes de crear recursos. Una ficha sin adaptador compatible no habilita instalación arbitraria.

Estados: `sin_preparar`, `preparando`, `lista_para_probar`, `lista_para_publicar`, `publicada`, `fallida`, `eliminando`, `eliminada`. El frontend consulta mientras se prepara/elimina y muestra progreso y errores seguros. El revelado de acceso conserva el endpoint administrativo auditado existente y no se incluye en las respuestas de estado.

## Comprobación simple

El servidor registra la comprobación con el marcador explícito `simple_verification`: artefacto saneado, despliegues e identidades comprobados, credenciales independientes y confirmación funcional del administrador. No atribuye ensayos de exportación, reinicio, aislamiento cruzado o bloqueo del proveedor que no se realizaron. Las validaciones antiguas sin ese marcador conservan su conjunto completo de checks.

La migración `010_04_preparacion_simple` permite fechas nulas y quita deadlines de preparaciones activas anteriores y sus reservas/operaciones. Conserva plazos históricos cerrados y las fechas académicas. No reabre preparaciones ya vencidas.
