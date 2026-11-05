# Quickstart: validar la terminal web del portal

Prerrequisitos: laboratorio encendido con quórum y NFS, maestros SSH abiertos, paquete de nodo con `nap-console-identity/1` instalado en **todos** los nodos antes que el portal, evidencia real de revocación vigente (feature 020) y un Linux IaaS encendido en cada nodo.

1. **Aprovisionamiento**: crear una persona nueva asignada a una cátedra; sin ninguna acción manual, su identidad pasa a `lista` (administración la ve en «Identidades de consola»).
2. **Terminal**: con un navegador que sólo llega al portal (sin ruta a los nodos), abrir «Ver acceso → Abrir terminal» de un Linux de **cada** nodo, iniciar sesión como `nap` y ejecutar `sudo`. No aparece ninguna pantalla de Proxmox.
3. **Aislamiento**: la misma persona es rechazada en un servicio de otra cátedra; una persona sin identidad lista ve «todavía no está habilitado»; un servicio detenido explica el motivo.
4. **Límites**: dejar una terminal inactiva hasta que cierre; abrir terminales hasta el cupo y comprobar el rechazo de la siguiente; dar de baja el servicio con una terminal abierta y comprobar el corte inmediato.
5. **Retiro**: con una terminal abierta, retirar a la persona de la cátedra; la terminal se corta en < 5 s, no puede reabrir, su otra cátedra sigue funcionando; el trámite queda completado con evidencia automática.
6. **Adopción**: con la identidad creada a mano de una persona existente, comprobar que pasa a la gestionada sin perder acceso y que la manual desaparece.
7. **Secretos y contenido**: buscar la contraseña de la identidad y el texto tecleado en registros del portal, base, auditoría y nodos: no aparecen.
8. **Limpieza**: bajas de los servicios de prueba y retiro de las personas de prueba.

Pruebas automáticas: `pytest infra/runner/tests backend/tests/test_terminal_022.py backend/tests/test_identidades_consola_022.py` y `vitest` del frontend.
