# Feature Specification: Usuario no root en la consola de Linux IaaS

**Feature Branch**: `021-consola-usuario-no-root`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Usuario no root para el acceso por consola de servicios IaaS Linux. Hoy, al abrir la consola de un Linux IaaS, la persona entra al contenedor como root con la contraseña del «acceso inicial» (la que genera el portal al desplegar y aplica el bootstrap del servicio Linux a root); el usuario nap, creado por la feature 017 con sudo, tiene la contraseña bloqueada y sólo sirve por SSH con clave. Eso es inconsistente con el endurecimiento de la 017 (sin root por SSH) y obliga a usar la cuenta root directamente. Se quiere que la consola use el usuario nap: que el acceso inicial que muestra el portal sea la contraseña de nap, que root quede sin contraseña utilizable, que sshd siga sin aceptar contraseñas (la contraseña sólo sirve en la consola) y que las acciones privilegiadas pasen por sudo a nombre de nap. Debe aplicar a servicios nuevos y a los ya entregados (por la operación de reparación existente, sin crear un servicio nuevo ni perder datos), con la contraseña nunca visible en registros ni errores y entregada sólo por Revelar acceso inicial. Fuera de alcance: la compuerta de consola y las identidades de Proxmox (feature 020), terminal web propio, nuevos usuarios además de nap, cambios a servicios Docker/OCI, rotación periódica de contraseñas."

<!-- Principio I: no abre excepciones nuevas ni toca la derivación a la consola (spec 020). Principio VII: la persona no aporta
     datos nuevos; usa el mismo «Revelar acceso inicial», que ahora muestra el usuario correcto. Principio III: el cambio en servicios
     ya entregados usa la operación de reparación existente (durable, idempotente por revisión). -->

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entrar a la consola como un usuario normal (Priority: P1)

Una persona de cátedra abre la consola de su Linux IaaS y entra con el usuario `nap` y la contraseña que muestra «Revelar acceso inicial». Una vez dentro, hace lo que necesita con `sudo`; nunca trabaja directamente como administrador del sistema. El usuario que el portal muestra junto a la contraseña es `nap`, no `root`.

**Why this priority**: Es el resultado visible y el motivo de la feature: hoy la consola obliga a usar la cuenta de administración del contenedor, en contradicción con el acceso por SSH, que ya la excluye.

**Independent Test**: Desplegar un Linux IaaS nuevo, revelar el acceso inicial, abrir la consola e iniciar sesión como `nap`; ejecutar un comando con `sudo`; intentar iniciar sesión como `root` con esa y con cualquier contraseña y comprobar el rechazo.

**Acceptance Scenarios**:

1. **Given** un Linux IaaS nuevo disponible, **When** la persona usa «Revelar acceso inicial», **Then** el portal muestra el usuario `nap` y su contraseña, y no menciona a `root`.
2. **Given** esa contraseña, **When** la persona inicia sesión en la consola como `nap`, **Then** entra y puede ejecutar acciones privilegiadas con `sudo`.
3. **Given** el mismo servicio, **When** alguien intenta iniciar sesión como `root` en la consola con cualquier contraseña, **Then** es rechazado.
4. **Given** el mismo servicio, **When** alguien intenta entrar por SSH con contraseña (como `nap` o como `root`), **Then** el servicio lo rechaza: la contraseña sólo sirve en la consola; el acceso por SSH con clave sigue funcionando como antes.
5. **Given** una acción privilegiada hecha con `sudo`, **When** se revisa el registro del sistema, **Then** queda atribuida al usuario `nap`.

---

### User Story 2 - Pasar los servicios ya entregados al usuario normal (Priority: P1)

Los Linux IaaS que ya existen entran por consola con `root`. Un administrador los actualiza al modelo nuevo sin dar de baja ni volver a pedir el servicio: el servicio conserva su disco, sus datos, su clave SSH y su dirección. Después de la actualización la persona entra como `nap` con una contraseña nueva y la de `root` deja de servir.

**Why this priority**: Sin esto, la mejora sólo alcanzaría a servicios futuros y los entregados seguirían con el acceso que se quiere retirar. Es parte del mismo resultado.

**Independent Test**: Con un servicio entregado y en uso, aplicar la actualización, comprobar que los datos y la clave SSH siguen igual, que `nap` entra por consola con la contraseña nueva y que la contraseña anterior de `root` ya no sirve.

**Acceptance Scenarios**:

1. **Given** un servicio entregado con contraseña de `root`, **When** administración lo actualiza, **Then** `nap` queda con una contraseña nueva, `root` sin contraseña utilizable, y no se crea otro servicio ni cambian su disco, dirección ni clave SSH.
2. **Given** un archivo guardado por la persona dentro del contenedor, **When** se actualiza el servicio, **Then** el archivo sigue ahí con el mismo contenido.
3. **Given** un servicio ya actualizado, **When** se repite la actualización, **Then** no cambia nada ni se invalida una contraseña que la persona ya reveló (la operación es idempotente).
4. **Given** un servicio detenido o sin respuesta, **When** se intenta actualizar, **Then** el portal explica que no se pudo y mantiene el estado anterior sin dejar el acceso a medias.
5. **Given** una persona que conocía la contraseña de `root`, **When** el servicio se actualiza, **Then** la consola ya no admite esa contraseña y el portal lleva a «Revelar acceso inicial» para obtener la nueva.

---

### User Story 3 - La contraseña nunca se expone fuera de «Revelar acceso inicial» (Priority: P2)

La contraseña de `nap` se entrega únicamente a quien está autorizado, en el momento en que lo pide, y no aparece en registros, mensajes de error, auditoría ni pantallas intermedias. Cada revelación queda auditada sin guardar el valor.

**Why this priority**: Protege el resultado de las historias 1 y 2; el comportamiento de entrega ya existe, pero cambia el usuario al que corresponde, y no debe abrir una vía nueva de filtración.

**Independent Test**: Desplegar y actualizar servicios provocando fallos intencionales; comprobar que la contraseña no aparece en ningún registro, error ni auditoría, y que sólo la ve quien tiene autorización sobre el servicio.

**Acceptance Scenarios**:

1. **Given** un despliegue o una actualización con fallo, **When** se revisan registros, errores y la auditoría, **Then** la contraseña no aparece en ninguno.
2. **Given** una persona de otra cátedra, **When** intenta revelar el acceso del servicio, **Then** se le rechaza como hoy.
3. **Given** una revelación válida, **When** se consulta la auditoría, **Then** consta quién, cuándo y qué servicio, sin el valor revelado.

---

### Edge Cases

- Un servicio entregado antes de la feature 017 que no tiene usuario `nap` (sin clave SSH): la actualización debe tratarlo según lo que defina el plan, sin dejarlo sin ningún acceso por consola.
- La persona perdió u olvidó la contraseña: se vuelve a obtener en «Revelar acceso inicial»; no hay recuperación por otra vía.
- El servicio se reinicia o el nodo cae durante la actualización: el resultado incierto se reintenta sin duplicar efectos y sin dejar a `root` con contraseña si ya se retiró ni a `nap` sin ella.
- Debian 13 además de Ubuntu 24.04: ambas bases ofrecidas deben comportarse igual.
- Un servicio Docker/OCI no se modifica; sólo aplica a Linux IaaS.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El acceso inicial de un Linux IaaS MUST corresponder al usuario `nap`: «Revelar acceso inicial» muestra el usuario `nap` y su contraseña, y no la de `root`.
- **FR-002**: La contraseña de `nap` MUST permitir iniciar sesión en la consola del contenedor y MUST NOT ser aceptada por SSH: el servicio sigue sin aceptar contraseñas por SSH (ni para `nap` ni para `root`).
- **FR-003**: `root` MUST quedar sin contraseña utilizable en el contenedor: ninguna contraseña le permite iniciar sesión en la consola.
- **FR-004**: Las acciones privilegiadas de la persona MUST hacerse con `sudo` desde `nap`, y MUST quedar atribuidas a `nap` en el registro del sistema.
- **FR-005**: Para servicios nuevos, el contenedor MUST quedar con este modelo desde la primera vez que está disponible, sin un paso posterior de la persona.
- **FR-006**: Para servicios ya entregados, administración MUST poder aplicar el nuevo modelo mediante la operación de reparación existente, sin crear un servicio nuevo y conservando disco, datos, clave SSH y dirección.
- **FR-007**: La actualización MUST ser idempotente: repetirla no cambia el resultado ni invalida una contraseña ya revelada, y un resultado incierto se reintenta sin duplicar efectos.
- **FR-008**: Tras actualizar un servicio, la contraseña anterior de `root` MUST dejar de funcionar, y el portal MUST indicar con claridad que hay que obtener el acceso nuevo.
- **FR-009**: La contraseña MUST NOT aparecer en registros, mensajes de error, auditoría ni respuestas distintas de «Revelar acceso inicial»; cada revelación MUST quedar auditada sin el valor.
- **FR-010**: La entrega MUST seguir limitada a quien ya está autorizado sobre el servicio; una cátedra ajena MUST seguir siendo rechazada.
- **FR-011**: La indicación de la consola en el portal MUST decir que se entra como `nap` con la contraseña de «Revelar acceso inicial», sin mencionar `root`.
- **FR-012**: Si no se puede completar la actualización, el servicio MUST quedar en su estado anterior o consistente (nunca con ambas cuentas sin contraseña), con un motivo comprensible para administración.
- **FR-013**: El comportamiento MUST ser el mismo para todas las bases Linux IaaS ofrecidas (Ubuntu 24.04 y Debian 13).
- **FR-014**: No se modifica la compuerta de consola ni las identidades de infraestructura (feature 020), ni el acceso por SSH con clave (feature 017), ni los servicios Docker/OCI.

### Key Entities

- **Acceso inicial del servicio**: credencial entregada a la persona en «Revelar acceso inicial»; pasa a ser la del usuario `nap` y se genera y guarda cifrada, nunca en claro.
- **Servicio Linux IaaS**: contenedor con usuario `nap` (clave SSH y `sudo`) y, tras esta feature, contraseña propia para la consola y `root` sin contraseña.
- **Operación de reparación**: operación durable y con revisión que actualiza un servicio entregado al modelo nuevo.
- **Auditoría de revelación**: registro de quién reveló el acceso de qué servicio y cuándo, sin el valor.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En un Linux IaaS nuevo, una persona obtiene el acceso, abre la consola y trabaja con `sudo` como `nap` en menos de 2 minutos desde que el servicio está disponible, sin ayuda.
- **SC-002**: El 100 % de los intentos de iniciar sesión como `root` en la consola, y de iniciar sesión por SSH con contraseña, son rechazados (comprobado con al menos 3 intentos de cada tipo).
- **SC-003**: Al actualizar un servicio entregado, el 100 % de sus archivos y de su clave SSH se conservan, y la contraseña anterior de `root` deja de servir en la primera comprobación.
- **SC-004**: Repetir la actualización 3 veces seguidas sobre el mismo servicio no cambia la contraseña de `nap` ya revelada.
- **SC-005**: Una búsqueda en registros, errores y auditoría de despliegues y actualizaciones, incluidos los que fallaron a propósito, no encuentra la contraseña en ningún caso.
- **SC-006**: El 100 % de las acciones privilegiadas hechas por la persona en una prueba quedan atribuidas a `nap` en el registro del sistema.

## Assumptions

- La contraseña de `nap` se genera de forma aleatoria al desplegar o actualizar y se conserva cifrada, como hoy la de `root`; la persona no la elige.
- `sudo` de `nap` sigue sin pedir contraseña, como lo dejó la feature 017; quitar ese permiso es otra decisión y no forma parte de esta feature.
- `root` queda sin contraseña utilizable pero la cuenta sigue existiendo (así funcionan las tareas del sistema); no se elimina.
- Los servicios entregados que no tengan usuario `nap` (anteriores a la 017) se tratan con lo que defina el plan; no se asume que existan.
- La actualización de servicios existentes la dispara administración y la persona obtiene el acceso nuevo en «Revelar acceso inicial».
- Se reutilizan la operación de reparación, el cifrado de credenciales y la auditoría de revelaciones existentes.
- El paquete de nodo del laboratorio se reinstalará para verificar el cambio; que esto modifique o no la firma de política del motor Docker es una restricción de diseño que decide el plan (la 017 pidió no alterarla).
