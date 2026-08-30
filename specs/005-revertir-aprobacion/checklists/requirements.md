# Specification Quality Checklist: Revertir una aprobación antes del despliegue

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

Revisión hecha sobre la spec escrita el 2026-08-30.

**Sobre implementación en el texto**: la spec nombra estados del dominio ("aprobado",
"solicitado") y el hecho de que la transición ya existe en la máquina de estados. Se
consideró aceptable y no una fuga de implementación: la máquina de estados es
vocabulario de negocio en este proyecto —el Principio II la declara la única fuente de
verdad y la cátedra ve esos estados en pantalla—, no un detalle técnico interno. Los
nombres de símbolos del código (`TRANSICIONES_SISTEMA`, códigos HTTP, nombres de
trabajos) quedaron confinados al bloque **Input**, que es cita textual del pedido
original, y a la sección **Contexto de origen**, que documenta cómo se descubrió.

**Sobre las cinco preguntas de Clarifications**: se resolvieron con decisión tomada en
lugar de dejar marcadores, porque todas tenían un default defendible a partir de los
principios vigentes (distinguir reversión de rechazo se sigue del Principio V; prohibir
la reversión con despliegue en curso, del III; restringirla al administrador, del VI).
Ninguna quedó abierta.

**Ambigüedad deliberada**: la spec no fija **a qué estado** queda el pedido revertido, ni
si se reutiliza `rechazado` con una marca o se introduce uno nuevo. Es una decisión de
diseño que corresponde a `/speckit-plan`, no a la especificación; lo que la spec sí exige
(FR-009) es que el resultado sea distinguible de las otras dos formas de terminar.

**Riesgo señalado para la fase de plan**: FR-004 (atomicidad) y FR-005 (concurrencia)
activan la compuerta constitucional de pruebas de concurrencia sobre código que decide
capacidad. El plan debe preverlo explícitamente.
