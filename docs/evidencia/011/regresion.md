# Evidencia de regresión transversal — Feature 011 (T099)

Fecha: 28/10/2026  
Rama: `011-desplegar-servicios-universitarios`  
Alcance: Comprobación de no regresión sobre servicios previos (IaaS Ubuntu 24.04 / Debian 13, Draw.io legacy 010, renovaciones, consola interactiva Proxmox e historial de pedidos) tras la integración del motor Docker OCI y el catálogo unificado.

---

## 1. Resumen de ejecución

| Suite | Archivo | Casos | Tiempo | Resultado |
|---|---|---|---|---|
| Backend Pytest | `backend/tests/test_regresion_servicios_011.py` | 5 | 6.29 s | **5/5 Aprobadas** |
| Frontend Playwright | `frontend/tests/e2e/regresion-servicios-011.spec.js` | 4 | 7.0 s | **4/4 Aprobadas** |

Comandos de ejecución ejecutados:
```bash
# Suite backend
backend/venv/bin/python -m pytest -c backend/pytest.ini -v backend/tests/test_regresion_servicios_011.py

# Suite frontend E2E
npm --prefix frontend run test:e2e -- tests/e2e/regresion-servicios-011.spec.js
```

---

## 2. Áreas verificadas

### 2.1 IaaS Ubuntu 24.04 y Debian 13
- **Sincronización declarativa**: `bases_iaas_service.sincronizar` detecta plantillas vztmpl en almacenamiento Proxmox y las sincroniza en la base de datos sin requerir archivos de definición de aplicación externos.
- **Flujo docente simplificado**: Solicitud con formulario académico cotidiano (sin campos crudos, UUIDs ni JSONs técnicos).
- **Aprobación y despliegue**: Reserva atómica de capacidad en nodo y storage, asignación de IP estática mediante perfil de red, creación del contenedor no privilegiado y generación segura de contraseña `root` mediante el keyring del sistema.
- **Consola interactiva IaaS**: `/servicios/{id}/consola` entrega URL segura hacia la consola xterm.js de Proxmox exclusivamente tras validar rol, estado `running`, vigencia activa e identidad propia confirmada, sin colisionar con la consola de operaciones de despliegue (`/operaciones/{id}/consola`).

### 2.2 Draw.io y aplicaciones SaaS previas (010)
- **Compatibilidad de manifiestos y runner legacy**: Solicitud y despliegue de Draw.io utilizando manifiesto y runner de versión 010. Se verificó que el despachador ejecuta el protocolo correspondiente a la definición sin desviar la ejecución al motor OCI ni alterar las expectativas de la versión previa.
- **Acceso por Gateway NAP**: Entrega de servicio SaaS a través de gateway HTTPS local (`app-<id>.nap-apps.test`), entrega de credenciales/códigos de un solo uso sin exposición de contraseñas de infraestructura ni contaminación de cookies hacia el portal.

### 2.3 Renovaciones sin recreación de instancias
- **Extensión de vigencia**: Un pedido de tipo `RENOVACION` sobre un servicio activo extiende el período autorizado sin destruir ni recrear el contenedor en Proxmox (`vmid` idéntico, identidad de infraestructura idéntica).
- **Conservación de secretos y red**: Los secretos de aplicación, las contraseñas cifradas y la IP/MAC asignadas se mantienen inalteradas.
- **Contabilidad de capacidad limpia**: La renovación no realiza doble reserva de capacidad sobre un servicio que ya se encuentra contabilizado.

### 2.4 Aislamiento operativo y no interferencia
- Operaciones de ciclo de vida (`stop`, `start`, `restart`) ejecutadas sobre una instancia no modifican el estado, los recursos ni las identidades de servicios pertenecientes a otras cátedras o nodos.

---

## 3. Conclusión de regresión

La feature 011 mantiene compatibilidad plena con el comportamiento y contratos de versiones anteriores (IaaS, SaaS Draw.io y ciclo de vida de pedidos/servicios). Ninguna funcionalidad preexistente se vio degradada ni alterada por el soporte de imágenes Docker Hub y registries OCI.

