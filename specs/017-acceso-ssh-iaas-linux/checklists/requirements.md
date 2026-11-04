# Specification Quality Checklist: Acceso SSH a servicios IaaS Linux

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-03
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

## Notes

- Aclaraciones resueltas (03/11): Q1 = A (servicios ya entregados pueden incorporar clave); Q2 = B (usuario sin privilegios con elevación, sin ingreso directo como administrador).
- Constitución: no exige enmienda. El acceso no deriva a Proxmox ni usa sus permisos (Principio I); la excepción de la consola interactiva queda intacta (FR-015).
- Efecto en el motor: requiere reinstalar el paquete de nodo y validar con ensayo real; no cambia el `policy_digest` de los perfiles Docker (el módulo nuevo queda fuera de sus entradas).
- Corrección 03/11: los servicios Linux IaaS no tienen aislamiento de red por instancia ni lista de clientes permitidos (existe sólo en el motor Docker/OCI); FR-008 y SC-003 ya no los invocan.
