# Specification Quality Checklist: Retirar y corregir usuarios, cátedras y plantillas

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-30
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
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

## Notas de la validación

**Sobre agrupar tres defectos en una sola spec**: se evaluó separarlos. Se mantuvieron
juntos porque comparten causa (el portal sabe crear entidades administrativas pero no
retirarlas ni corregirlas), porque las tres decisiones de diseño se apoyan en la misma
lectura del Principio V, y porque las tres historias son independientes entre sí —se
puede implementar solo la US1 y ya hay valor entregado, que es el criterio del template.

**Sobre por qué no fueron a la spec 005**: 005 tiene un alcance acotado a la reversión de
aprobaciones y su checklist declara ese límite. Sumarle defectos de otra naturaleza lo
habría roto.

**Ambigüedades deliberadas, que corresponden a `/speckit-plan`**:

- No se fija si "retirar una persona" reutiliza el campo de activación que ya existe o
  introduce otro concepto. Lo que la spec exige (FR-011, FR-012) es el comportamiento
  observable.
- No se fija qué pasa exactamente con un pedido aprobado sin desplegar cuando su plantilla
  se corrige (edge case registrado). Es una decisión de diseño con implicancias sobre la
  contabilidad de capacidad, y merece resolverse en el plan, no acá.

**Riesgo señalado para la fase de plan**: el edge case de corregir una plantilla con un
pedido aprobado pendiente toca la contabilidad de capacidad de la feature 004, lo que
activa la compuerta constitucional de pruebas sobre código que decide capacidad.

**Cobertura de los hallazgos de T091**: los tres defectos abiertos quedan cubiertos —
borrado de usuario con historial (US2), mensaje de bloqueo engañoso (US3), plantillas no
editables ni retirables (US1). El cuarto hallazgo de esa tanda, el arranque abortado con
más de un administrador, se corrigió en el momento y por eso no figura acá.
