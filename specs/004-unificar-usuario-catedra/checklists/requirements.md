# Specification Quality Checklist: Unificación usuario–cátedra y control de recursos por aprobación

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — los 7 puntos se resolvieron en sesión
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- **6 historias de usuario, 58 requisitos funcionales (agregados 6 para alta de usuario), 11
  criterios de éxito, 13 riesgos, 24 edge cases (agregados 6).** Sin marcadores pendientes.
- **Bloqueante de gobernanza**: bump a 2.0.0 de la constitución. Ejecutar `/speckit-constitution`
  **antes** de `/speckit-plan`.
- **Decisiones de diseño UI agregadas**: patrón one-shot para crear usuario + asignar cátedras,
  usando un buscador limpio con checkboxes (FR-035b a FR-036c). Incluyó validación atómica,
  filtrado de cátedras ya asignadas, y resumen de confirmación.
- Decisiones de negocio (incorporadas en sesiones):
  1. Titular único por cátedra
  2. Pausado automático
  3. Advertencia sin bloqueo + justificación
  4. Detención (no hibernación) para "pausar"
  5. Contabilidad de capacidad sí, techo por cátedra no
  6. Aprobación reserva capacidad de forma atómica
  7. Vencimiento por servicio + pausado por inactividad
- Los riesgos 4 y 13 son costos aceptados; los 11 restantes están trazados a requisitos.
