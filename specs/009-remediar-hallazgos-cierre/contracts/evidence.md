# Registro e importación de evidencias

Contrato implementado en el repositorio (`009-remediar-hallazgos-cierre`). Prefijo `/api/v1`; sesión operativa admin, CSRF/Origin e idempotencia según [auth.md](auth.md) y [operations.md](operations.md). Productores: operador de pruebas de red, builder técnico y operador institucional de consola. Ninguno necesita credenciales del portal en la imagen o el runner.

## Interfaces y almacenamiento

| Método y ruta | Permiso | Resultado |
|---|---|---|
| `POST /evidencias` | Admin | 201 con `evidencia_ref` UUID, `sha256`, `tipo`, `registrada_por` y `registrada_at`; requiere Idempotency-Key. Importa el documento, sin ejecutar pruebas ni habilitar el recurso. |
| `GET /evidencias/{id}` | Admin | 200 con documento y metadatos; Cache-Control: no-store. Docente recibe 403. |

No hay actualización ni borrado de evidencias. El formulario admin permite importar JSON local o completar la misma estructura; el archivo se lee en el navegador y se envía su contenido, nunca una ruta del servidor. El builder entrega un JSON al operador; este lo importa con su sesión administrativa. La API no acepta referencias mediante URL, archivos binarios, HTML ni comandos y no descarga artefactos externos. El endpoint del servicio se almacena solo como dato resuelto y se rechaza si contiene credenciales; no se visita desde el registro.

El cuerpo cumple [evidence.schema.json](evidence.schema.json), Draft 2020-12 con comprobación de formatos, campos desconocidos prohibidos y límite de 64 KiB UTF-8 antes de parsear. Rechazar claves duplicadas, BOM, floats y números no finitos, JSON inválido, fechas futuras y cualquier campo de credenciales/cookies/tickets/nonce en claro. `registrada_por` y `registrada_at` los obtiene el servidor de la sesión/reloj: no son campos de entrada. `operador_institucional` y `referencia_institucional` documentan la declaración del ejecutor y el registro del ensayo, sin datos personales sensibles ni secretos.

Persistir `evidencias` en PostgreSQL con UUID aleatorio, documento canónico inmutable y SHA-256. Canonizar recursivamente claves ordenadas, UTF-8, sin espacios ni escape ASCII innecesario (`ensure_ascii=false`), enteros, sin salto final. Digest solo del documento recibido canónico; metadatos del servidor separados. Recalcular digest al leer/consumir y rechazar una alteración; las restricciones de la cuenta DB y del servicio impiden mutación ordinaria. No se considera firma digital ni prueba independiente de que se ejecutó una observación: el registrante admin asume la declaración institucional auditada.

Errores: 413 por tamaño; 422 por formato/tipo/identidad inválidos, destino inexistente o fecha futura; 409 por revisión/nonce/preparación/digests desactualizados; 403 por rol. En registro se comprueba el destino y su revisión existentes; cada consumidor repite esas validaciones bajo lock antes de cambiar estado. Simulaciones se admiten solo en entorno de pruebas aislado; en operación, importar `entorno=simulado` devuelve 422 y nunca publica, entrega ni completa una revocación. Repetir Idempotency-Key devuelve mismo UUID, sin otra fila; la misma evidencia puede releerse pero no habilitar un destino diferente.

## Documentos por tipo

Todos incluyen `schema_version=1`, `tipo`, `entorno`, `operador_institucional`, `referencia_institucional`, `observado_at` UTC con Z y `resultado` tipado. Registrar sin resultados satisfactorios se rechaza; los ensayos fallidos quedan en la bitácora del ensayo/trámite, no son evidencia habilitante.

- **acceso_instancia**: servicio y definición registrados, `resource_uuid`, `nonce_sha256` del nonce de identidad, `preparacion_id` UUID de la operación de preparación confirmada, endpoint resuelto, equipo/red de origen, método manual y lista de pruebas funcionales satisfactorias. Operador obtiene la identidad y el hash desde el detalle administrativo, sin revelar nonce en claro. Tras el recorrido desde la red prevista, importa el documento y pasa el UUID devuelto a `POST /servicios/{id}/verificar-acceso`; endpoint e instante enviados allí coinciden exactamente con el artefacto. Rechazar evidencia anterior a la preparación vigente, sin vigencia, de otra instancia o con pruebas que no cubran el producto. Un código HTTP o ping aislado no completa las pruebas. Linux exige `login_consola`, `sudo_local` y compuerta institucional de consola; PostgreSQL `conexion_autenticada`, `escritura_lectura`, `persistencia`; BookStack `publicacion_docente`, `lectura_individual`, `persistencia`, `permisos_lectores`, `revocacion_individual`, `archivos_privados`, verificadas por instancia.
- **validacion_definicion**: ID/código/versión del borrador previamente creado, SHA-256 de imagen y receta, clúster/versiones PVE, al menos dos `resource_uuid` de laboratorio distintos y checks satisfactorios exigidos por el producto. Estas instancias iniciales no necesitan existir como servicios NAP. El builder calcula esos resultados antes de importar; se comprueban disponibilidad e integridad de imagen/receta en el repositorio institucional según catalog-ui.md. El manifiesto copia UUID y digest del registro a `validation.evidence_id/evidence_sha256`; los demás campos de validation (fecha, clúster/versiones, cantidad/checks) coinciden con el artefacto. El digest no incluye el manifiesto, evitando dependencia circular. El consumidor rechaza otra versión, imagen o receta y usa la allowlist de checks del schema de definición.
- **revocacion_consola**: ID del trámite, revisión esperada, identidad PVE y scopes resultantes exactos del trámite. Incluye comprobación de cierre de sesiones previas, denegación mediante URL directa y conservación de otros accesos legítimos. Lo importa el admin después de la ejecución y prueba institucional descrita en console-access.md. No se acepta un booleano suelto para cambiar la titularidad.

Ejemplo de acceso (datos ficticios; no constituye aceptación real):

~~~json
{
  "schema_version": 1,
  "tipo": "acceso_instancia",
  "entorno": "real",
  "operador_institucional": "operador-laboratorio",
  "referencia_institucional": "ACTA-RED-009",
  "observado_at": "2027-03-01T12:10:00Z",
  "resultado": {
    "servicio_id": 9,
    "definicion_id": "01900000-0000-4000-8000-000000000001",
    "resource_uuid": "01900000-0000-4000-8000-000000000002",
    "nonce_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "preparacion_id": "01900000-0000-4000-8000-000000000003",
    "endpoint": "https://libros-catedra.example.edu",
    "equipo_origen": "laboratorio-01",
    "red_origen": "red-alumnos",
    "metodo": "manual",
    "pruebas": [
      "publicacion_docente",
      "lectura_individual",
      "persistencia",
      "permisos_lectores",
      "revocacion_individual",
      "archivos_privados"
    ]
  }
}
~~~

Pruebas exigidas: UUID inexistente, acceso docente denegado, payload sobredimensionado/extra/duplicado, manipulación del JSON almacenado, idempotencia, simulación en operación, destino o revisión incorrectos, nonce/preparación anteriores, resultados incompletos y referencias cruzadas entre tipos. Ningún listado ni log incluye secretos de los recorridos.
