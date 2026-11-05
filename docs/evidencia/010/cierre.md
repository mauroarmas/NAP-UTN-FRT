# Estado de implementación 010

**Implementación local realizada; piloto operativo todavía no aceptado.** Los cambios están en el árbol de trabajo y no se publicaron ni desplegaron. Se preservaron las modificaciones de diseño existentes al iniciar.

Se completaron **69 de 73 tareas**. Permanecen abiertas **T052** (ensayo real), **T067** (entregas reales), **T072** (tiempos humanos/carga) y **T073** (cierre formal condicionado a esas compuertas). Este documento registra el estado parcial de cierre; no da esas tareas por ejecutadas. No hay hooks `after_implement` configurados.

| Requisito | Implementación / evidencia local | Aceptación pendiente |
|---|---|---|
| FR-001–FR-005 | Biblioteca administrativa, fuente oficial sólo lectura, filtros/alias, cache/errores, incorporación deduplicada y CAS; `us1-incorporacion.md` | SC-001 humano con proveedor disponible |
| FR-006 | Adaptador cerrado Draw.io 1.1, sin ejecutor genérico ni comandos externos; `us2-pruebas.md` | Imagen real con revisión comprometida |
| FR-007–FR-008 | Pipeline, manifiesto/locks/digests, saneamiento, dos LXC y evidencia obligatoria; publicación bloqueada si falta comprobación | T052: edición/perímetro/aislamiento/despliegue sin proveedor reales |
| FR-009 | Publicación atómica y perfil estable versionado; bitácora inmutable, limpieza separada | Acreditar oferta real con T052 |
| FR-010 | Catálogo y Pedidos Software, sin selección de hardware; pruebas UI y navegador | Medición humana desde ambas entradas |
| FR-011 | Selección original, vigente al aprobar, comparación y aviso; snapshot posterior congelado | Recorrido real de aprobación/entrega |
| FR-012 | Dos cátedras e instancias/credenciales distintas y acceso cruzado denegado con dobles | T067: dos entregas reales |
| FR-013 | Idempotencia, leases, generación/tombstone remoto, respuesta perdida, reinicio; `us2-pruebas.md` y `us3-pruebas.md` | Fallos reales controlados en staging |
| FR-014 | Retención de artefactos/historia y bootstrap sin fuente externa; ofertas retiradas no mutan aprobaciones | SC-006 con pedido real y proveedor bloqueado |
| FR-015 | «Otro» y renovaciones conservan contratos existentes, regresión backend/UI | Sin ampliación de alcance |
| FR-016 | Etiquetas/foco/teclado, errores y datos preservados; 49 pruebas UI / 32 navegador | Recorrido humano de aceptación |
| FR-017–FR-018 | Dos recursos institucionales, TTL/avisos/capacidad compartida, cancel/cleanup conservador y reintento; carreras PostgreSQL | T052: publicación/descarte/vencimiento reales |

| Criterio | Estado |
|---|---|
| SC-001 (<2 min incorporar) | Pendiente T072; no usar tiempos de Playwright como medición humana |
| SC-002 (no ofrecer incompletos) | Gate implementado y probado; falta acreditar la primera oferta real |
| SC-003 (ciclo editable y aislamiento) | Dobles y contrato pasan; pendiente T052/T067 |
| SC-004 (<3 min pedir) | Pendiente T067/T072 |
| SC-005 (repeticiones/confirmaciones perdidas) | Pruebas locales, órdenes fuera de orden, reinicio y concurrencia pasan; falta ejercicio real T052 |
| SC-006 (pedido durante caída de fuente) | Tests bloquean consultas a Community Scripts; pendiente pedido real T067 |

La configuración observada tiene cero builders/perfiles de ensayo y no tiene registro dinámico configurado. Seguir [instalación/operación](../../../infra/services/README.md#instalar-el-builder) y [quickstart](../../../specs/010-integrar-biblioteca-aplicaciones/quickstart.md), comprometer/revisar la receta y completar esas cuatro tareas. No se sustituyeron estos prerrequisitos por destinos, hashes o evidencias ficticios.

Resultados, comandos y límites de las pruebas en [regresion.md](regresion.md). El PostgreSQL utilizado fue exclusivamente el contenedor de pruebas y esquemas aleatorios protegidos; no se aplicaron migraciones a la base operativa. El head de código es `010_03_seleccion_oferta`.
