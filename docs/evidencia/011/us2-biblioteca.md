# US2: Docker Hub como biblioteca del motor OCI — Evidencia

## Componentes implementados (27/10/2026)

- **Descubrimiento Docker Hub** (`backend/app/services/biblioteca_service.py`):
  - Búsqueda en API v2 de Docker Hub (`https://hub.docker.com/v2/search/repositories/`) por nombre de repositorio o aplicación.
  - Paginación basada en cursor opaco verificado mediante hash criptográfico (SHA-256) del término de búsqueda. Un cursor manipulado o desactualizado devuelve error 409 explícito (`cursor_desactualizado`).
  - Distinción entre cero resultados (200 con `items: []`) y errores del proveedor:
    - 429 de Docker Hub -> 429 `limite_consultas_proveedor`.
    - Timeout o fallo de conexión -> 502 `proveedor_no_disponible`.
  - Distintivos y procedencia seguros: `oficial` (para imágenes oficiales de Docker Hub) y `comunidad`.
  - Categorías no bloqueantes: `GET /biblioteca/categorias` devuelve lista vacía segura (`items: []`), evitando errores ante APIs que no estructuran categorías en la búsqueda.
- **Rechazo de Community Scripts y preservación legacy**:
  - `POST /biblioteca/incorporaciones` devuelve 422 `community_scripts_retirado` para cualquier solicitud nueva de incorporación de script.
  - Se preserva la lectura histórica de registros existentes en `incorporaciones_aplicacion` mediante `GET /biblioteca/incorporaciones` y `GET /biblioteca/incorporaciones/{id}` para auditoría y Draw.io.
- **UI integrada** (`BibliotecaAplicaciones.jsx`, `AgregarServicioModal.jsx`, `AplicacionPropiaForm.jsx`):
  - Dos entradas unificadas: «Docker Hub» e «Imagen propia».
  - Búsqueda por nombre en Docker Hub con distintivo Oficial/Comunidad, descripción y botón «Agregar servicio».
  - La selección precarga `AplicacionPropiaForm` con el nombre de la aplicación, referencia de imagen (`repositorio:latest`) y descripción, sin pasos manuales de preparar, confirmar ni publicar.
  - En caso de fallo o rate-limit en la búsqueda, la interfaz ofrece la alternativa explícita de ingresar la referencia de imagen manualmente («Ingresar referencia manualmente»), conmutando a la entrada de imagen propia.

## Comprobaciones automatizadas

- **Backend** (`backend/tests/test_biblioteca_despliegue_011.py`):
  - 7 pruebas aprobadas en 6,40 s:
    1. `test_busqueda_autorizacion_y_campos_requeridos`: 401 sin auth, 403 cátedra, 422 sin término de búsqueda.
    2. `test_busqueda_docker_hub_exito_y_formato_items`: formato de repositorio, procedencia oficial/comunidad, distintivos y fuente.
    3. `test_busqueda_paginacion_cursor_y_tamper_rejected`: avance de página con cursor y rechazo con 409 ante cursor manipulado.
    4. `test_busqueda_cero_resultados_vs_errores_proveedor`: distinción de lista vacía (200), rate limit (429) y timeout/indisponibilidad (502).
    5. `test_categorias_docker_hub_no_bloqueantes`: lista vacía segura 200 sin excepción.
    6. `test_rechazo_nuevos_community_scripts_preservando_lectura_legacy`: 422 ante nuevo POST, lectura preservada de registros previos.
    7. `test_seleccion_hub_alta_propia_idempotente_sin_ct`: alta 201 reutilizando el motor OCI sin creación de LXC ni reserva de capacidad.
- **Frontend** (`frontend/tests/biblioteca-despliegue.test.jsx`, `frontend/tests/aplicacion-propia.test.jsx`):
  - 3 pruebas de biblioteca aprobadas en 4,14 s:
    1. Búsqueda por nombre con Docker Hub, procedencia y distintivos visibles, sin preparación/publicación.
    2. Selección de resultado que precarga formulario común de imagen Docker y agrega el servicio sin pasos intermedios.
    3. Fallo de búsqueda con mensaje de error y acción de ingreso manual de referencia hacia la pestaña de imagen propia.
  - 3 pruebas de formulario de imagen propia aprobadas en 3,52 s:
    - Alta breve sin hardware/preparación/publicación.
    - Error conservando campos y clave idempotente.
    - Opciones de persistencia y secretos sin pedir valores sensibles.
- **Regresiones verificadas**:
  - `backend/tests/test_templates_aplicaciones_011.py`: 9 pruebas aprobadas.
  - `backend/tests/test_biblioteca_fuente_010.py`, `test_biblioteca_pedidos_010.py`, `test_biblioteca_redaccion_010.py`: 10 pruebas aprobadas.
  - `frontend/tests/definiciones.test.jsx`: 4 pruebas aprobadas.

## Siguiente paso

- Validar el gate de Proxmox en el nodo y proceder con Phase 5 (US3: Solicitud por cátedra, Otro y agenda programada).

