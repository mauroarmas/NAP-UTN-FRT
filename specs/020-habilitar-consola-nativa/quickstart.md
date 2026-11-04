# Quickstart: validar la consola nativa en el laboratorio

Prerrequisitos: laboratorio encendido con quórum y NFS, maestros SSH abiertos, un Linux IaaS `RUNNING` con vigencia en cada nodo (frt y pve91), una persona de prueba de la cátedra 3. Detalle operativo en `docs/runbook-consola-nativa.md` (se escribe en la implementación).

1. **Rol e identidad** (operador): crear el rol de solo consola, una identidad individual y su ACL sobre `/pool/catedra-3`; comprobar que **no** ve nodos ni operaciones de energía.
2. **Inventario**: importar la identidad con `python -m scripts.importar_identidades_consola --archivo <json> --actor <operador> --referencia <acta>`.
3. **Ensayo de revocación**: abrir una consola real, retirar el acceso y registrar los tres resultados (sesión terminada, ticket rechazado, otro pool vigente). Si algún punto falla, detener: la consola queda cerrada (FR-008).
4. **Evidencia y trámite**: registrar la evidencia `revocacion_consola` y confirmar el trámite (`/admin/cambios-consola`).
5. **Habilitación**: cargar `console_access_profile` (contrato en [contracts/console-profile.md](contracts/console-profile.md)) y recrear api/worker.
6. **Verificación funcional** (SC-001, SC-002, SC-007): la persona abre la consola de un Linux de frt y de otro de pve91 desde el navegador; la misma cuenta es rechazada en una cátedra ajena; una cuenta sin identidad ve el mensaje claro; con un nodo apagado, la consola del otro sigue abriendo por el nodo vivo.
7. **Limpieza**: dar de baja los servicios de prueba y retirar identidades temporales con el procedimiento de revocación.

Pruebas automáticas: `pytest backend/tests/test_consola_destino_020.py backend/tests/test_consola_gate_020.py`.
