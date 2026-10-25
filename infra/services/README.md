# Preparar y operar productos de referencia

Estado al 20 de octubre de 2026: recetas y flujo local implementados. Las pruebas con dobles no acreditan imágenes instaladas, certificados, conectividad ni aceptación externa. T101/T102 permanecen pendientes. BookStack es el ejemplo provisional de libro virtual.

## Uso diario

Una **definición** fija software, versión, imagen, receta y pruebas. Un **perfil** asocia CPU/RAM/disco a esa definición. Cada **instancia** contiene los datos y credenciales de una cátedra. La preparación técnica inicial se realiza una vez por versión; solicitar y desplegar instancias usa el portal, sin instalar paquetes en cada guest.

1. Administración publica una versión validada en **Definiciones** y crea un perfil compatible en **Perfiles de recursos**.
2. El docente elige el perfil en **Catálogo**, cátedra y vigencia. Administración evalúa la selección explícita y aprueba.
3. Desde la fecha inicial se ordena desplegar. El worker crea LXC y prepara esa versión; la aprobación conserva imagen/receta y recursos aunque luego se retire del catálogo.
4. En **Servicios → Ver acceso**, administración revela el acceso inicial solo para validar. Prueba la instancia desde la red prevista, importa su evidencia y confirma la referencia por separado.
5. El pedido pasa a activo y el responsable puede revelar su acceso inicial. Un contenedor encendido o un probe local no completan la entrega.

QEMU conserva lectura histórica; no se ofrecen nuevas VMs. La consola Linux exige además el gate institucional de permisos/revocación T101.

## Qué preparar con infraestructura

Usar un host/VM de build Ubuntu 24.04 amd64 separado de los nodos operativos y sin datos privados. Requiere root para el chroot, Python 3.12 con dependencias del backend, Git y salida a repositorios autorizados. No ejecutar el builder sobre `/` o sobre el rootfs de una instancia existente.

Resolver y registrar antes del build:

- Rootfs oficial Ubuntu 24.04 amd64 y su SHA-256 verificado. Conservar procedencia/fecha y comprobación del archivo oficial; no usar una referencia flotante como identidad del artefacto.
- Revisión Git íntegra **comprometida** que coincida con common.py, receta, build.sh, builder y saneador. El build real rechaza código distinto de esa revisión. Este trabajo todavía está sin commits; no se realizó un build operativo.
- Lock completo de todos los paquetes del rootfs final, incluidos base y cierre de dependencias, con versiones exactas. El operador lo obtiene en una preparación aislada de la misma base y repositorios y lo revisa; el builder no resuelve silenciosamente un lock ni acepta un inventario diferente. Si cambia un paquete, crear/revisar otra versión.
- Destino de imagen LXC en PVE, almacenamiento rootdir, nodo, clúster UUID institucional, red/bridge/VLAN y rangos permitidos. DHCP/DNS/rutas/certificados los proporciona infraestructura.
- Cuenta SSH/forced-command/hostkeys/registro y clave montada en el worker conforme a [runner](../runner/README.md). Usar identidad nativa PVE individual y comprobar scopes, permisos heredados y revocación antes de habilitar consola.
- Para PostgreSQL/BookStack, host y dirección por resource_uuid, con certificado/clave/CA de instancia. Deben coincidir en el perfil del portal y el registro root del runner. Prepararlos antes de completar el bootstrap; si faltan, la operación conserva incertidumbre, datos y capacidad. No hay DNS/IPAM/CA automáticos.

La configuración real vive fuera del repositorio. `service_artifacts` indexa `definition_key:definition_version` con image_path, bundle_path, nodes y network_profile_id; `network_profiles` contiene bridge/nodes/allowed_cidrs/client_cidrs y, para aplicaciones, instances por UUID. `runner_nodes` indica host/user/port/private_key_path/known_hosts_path. Todos están vacíos por defecto; no copiar datos de ejemplos como evidencia de instalación.

### Ayudante para obtener el lock

Después de verificar SHA256SUMS y su firma oficial, importar **esa misma base** en Docker y conservar digest/ID. `resolve.Dockerfile` acepta la etiqueta de esa importación y un producto cerrado (`linux`, `postgresql`, `bookstack`):

```bash
docker build -f infra/services/resolve.Dockerfile \
  --build-arg BASE_IMAGE=ETIQUETA_DE_BASE_VERIFICADA --build-arg PRODUCT=linux \
  -t nap-resolved-linux infra/services
docker run --rm --network none nap-resolved-linux cat /opt/nap-resolution/linux.json
```

El JSON contiene inventario completo, `package_lock` y componentes observados, para revisar y preparar el plan. Repetir por producto. La imagen de resolución conserva el estado de instalación y **no se publica en PVE**; el constructor vuelve a partir de la base verificada, instala las versiones del lock y aplica saneamiento. La resolución no genera evidencia de despliegue/acceso ni sustituye los dos ensayos. Registro de la preparación local en [build-preparacion.md](../../docs/evidencia/009/build-preparacion.md).

## Build reproducible y saneamiento

Crear primero el borrador de definición en el portal y conservar su UUID. Preparar un plan JSON fuera del repositorio con exactamente:

| Campo | Contenido real requerido |
|---|---|
| schema_version | Entero 1 |
| definition_id | UUID del borrador registrado |
| base_sha256 | Digest del rootfs base verificado |
| source_date_epoch | Entero fijo registrado para esa construcción |
| package_lock | Objeto nombre de paquete → versión exacta; inventario completo |
| manifest | Objeto parcial del [contrato](../../specs/009-remediar-hallazgos-cierre/contracts/service-definition.schema.json), sin validation; con identidad, receta/revisión, mínimos, red, probes, paths y componentes |

`image.volume_id` termina en `.tar.gz`. Los digests image.sha256 y preparation.bundle_sha256 los calcula el builder; no inventarlos. Las versiones de PostgreSQL/PHP/MariaDB deben corresponder al lock. BookStack fija los valores de revisión/source/composer.lock de `bookstack/bootstrap.py`; el constructor los verifica contra los bytes oficiales. El esquema completo se exige al validar/publicar, no al guardar un borrador.

Desde la raíz del checkout en el host de build, con permisos de root y rutas institucionales existentes:

```bash
PYTHONPATH=backend:. backend/venv/bin/python -m infra.services.build_image build \
  --plan /srv/nap-build/plan.json \
  --base /srv/nap-build/base.tar.xz \
  --output /srv/nap-build/output/version-nueva \
  --execute
```

El directorio de salida debe ser nuevo. El builder verifica la base sobre los mismos bytes extraídos, no sigue escapes/enlaces al host, instala el lock en una copia privada y restaura su DNS guest. Limpia usuarios privados, bases previas, contraseñas, claves SSH/TLS, APP_KEY/.env, datos subidos, sesiones, caches, logs y estado de preparación; bloquea root/SSH y quita autologin. Genera imagen, recipe.tar.gz y manifest-draft.json. Los artefactos son de solo lectura; conservar todos y sus hashes. Un fallo no produce una versión publicada.

El contenido saneado se prueba antes de aceptarlo: no basta un flag del manifiesto. No usar la copia de una cátedra como plantilla maestra.

Para reconstruir sin descargar otra vez los mismos paquetes, el CLI admite `--apt-cache /srv/nap-build/cache`. Montar ese directorio solo lectura en el host efímero; contiene únicamente `.deb` de una resolución previa con procedencia conservada. El constructor copia archivos regulares acotados, rechaza enlaces y deja que APT compruebe sus hashes contra los índices firmados. El lock completo y la revisión Git siguen siendo obligatorios. Se omiten las traducciones del índice APT; las cachés de paquetes e índices se eliminan al sanear para no incorporarlas a la imagen final. Esto no convierte la imagen de resolución en una referencia publicable.

## Ensayos, evidencia y publicación

La validación inicial usa un destino de **staging institucional**, separado del catálogo aún no publicado. Infraestructura crea dos LXC de ensayo propios desde la imagen y ejecuta el mismo bundle mediante el runner autorizado, con marcas/UUID/nonce/digests, parámetros y secretos distintos. No instalar paquetes a mano en esos guests. Esto evita exigir publicar una definición antes de poder ensayarla. Los ensayos iniciales no son solicitudes aceptadas del portal; los dos despliegues finales de T102 sí usan el flujo del portal.

Registrar `trials.json` como array, una entrada por resource_uuid distinto. Cada entrada contiene exactamente resource_uuid, image_sha256, recipe_sha256, entorno, observado_at UTC y checks como objeto de resultados booleanos. Se requieren todos los checks BASE_CHECKS del builder; aplicaciones añaden unique_secrets y BookStack reader_permissions_and_revocation. Un resultado falso, identidad repetida o digest diferente bloquea la producción del documento.

```bash
PYTHONPATH=backend:. backend/venv/bin/python -m infra.services.build_image evidence \
  --manifest /srv/nap-build/output/version-nueva/manifest-draft.json \
  --trials /srv/nap-build/trials.json --output /srv/nap-build/evidence.json \
  --definition-id UUID_REGISTRADO --cluster-uuid UUID_INSTITUCIONAL \
  --operator OPERADOR_INSTITUCIONAL --reference REFERENCIA_DEL_ENSAYO \
  --pve-version VERSION_REAL --environment real
```

Sustituir los marcadores por valores observados; no se ejecutó este comando con infraestructura real. El productor valida coherencia de las declaraciones del operador, no realiza ni firma los ensayos por sí mismo. `simulado` sirve para pruebas aisladas y nunca habilita entrega operativa.

Guardar el borrador de manifiesto en Definiciones. Importar evidence.json con **Registrar evidencia institucional** y conservar la respuesta `{evidencia_ref, sha256}` como registration.json. Completar el manifiesto sin cambiar imagen/receta:

```bash
PYTHONPATH=backend:. backend/venv/bin/python -m infra.services.build_image finalize \
  --manifest /srv/nap-build/output/version-nueva/manifest-draft.json \
  --evidence /srv/nap-build/evidence.json --registration /srv/nap-build/registration.json \
  --output /srv/nap-build/manifest-complete.json
backend/venv/bin/python backend/scripts/validar_definicion.py /srv/nap-build/manifest-complete.json
```

Pegar el objeto de manifest-complete.json en **Manifiesto JSON**, guardar, validar y publicar con acciones separadas. La UI arma el sobre API `{"manifest": ...}`; el editor recibe solo el objeto interno. Conserva claves duplicadas para rechazo por el servidor. La validación comprueba UUID/hash/evidencia, dos ensayos, disponibilidad de imagen/bundle y perfiles. Instalar los archivos en sus ubicaciones institucionales y subir la misma imagen al storage PVE antes de validar. No hay publicación si falta un artefacto.

## Prueba de cada instancia

Después de preparar localmente, usar los metadatos administrativos de **Ver acceso** para servicio/definición/resource_uuid/nonce_sha256/preparacion_id/endpoint. La evidencia individual es distinta de la evidencia que publica una definición. Su [formato](../../specs/009-remediar-hallazgos-cierre/contracts/evidence.md) incluye equipo y red de origen, operador, referencia, observado_at y pruebas satisfactorias.

| Producto | Prueba desde otra computadora |
|---|---|
| Linux | Consola nativa limitada al recurso, login napadmin y sudo local; root bloqueado, sin autologin. Gate de ACL/sesiones previo. |
| PostgreSQL | TLS verify-full con CA institucional, rol/base de instancia, escritura/lectura y dato después de reiniciar. Sin superusuario/creación de roles/replicación ni conexión a otra instancia. |
| BookStack | Docente publica libro/página; dos lectores individuales solo leen; revocar uno impide su siguiente acceso y conserva el del otro; archivos sin sesión denegados; persistencia y aislamiento entre instancias. |

Importar el JSON y después pulsar **Confirmar verificación de acceso**. UUID, endpoint y fecha UTC deben coincidir con el documento. Una simulación, dato anterior a la preparación, otro recurso o referencia alterada no activa el pedido. El aviso no incluye claves; cada revelado posterior es deliberado y auditado. Las contraseñas iniciales pueden cambiar dentro de la aplicación y NAP no las sincroniza ni restablece al reintentar.

## Mantenimiento, variantes y retiro

Conservar definición/artefactos originales mientras haya aprobaciones o servicios que los referencien. Una actualización crea otra versión, con lock/digests y dos ensayos nuevos. Cambiar el perfil afecta ofertas futuras, no el snapshot aprobado. Un retiro ordinario impide nuevas solicitudes y conserva instancias/datos; `security_blocked` es un bloqueo técnico explícito diferente y exige revisión antes de reanudar una preparación.

Se puede registrar otro perfil o definición compatible de Linux o PostgreSQL 16, con recursos/paquetes/versiones admitidos y otra validación, sin cambiar los pedidos. Una aplicación distinta de las tres recetas cerradas requiere receta, contrato, probes, saneamiento y pruebas nuevos; no se acepta un script arbitrario por el manifiesto. BookStack 26.09.1 está fijado: una release diferente exige revisar la receta/contrato además de publicar otra definición. No se promete un marketplace de instaladores libres.

Respaldos: infraestructura coordina copias externas y restauración separada. PostgreSQL conserva dump/roles/configuración; BookStack base MariaDB consistente, `.env`/APP_KEY, imágenes/adjuntos y temas. Conservar keyring/estado del portal y runner. Una copia del portal no respalda contenido de aplicaciones. Los ensayos de restore T131/T133 siguen pendientes; no llamar recuperación probada a un reinicio o a un archivo de dump sin restaurar.

## Pruebas locales

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests
```

Por defecto no hay procesos externos, red, PVE ni SMTP. Los cuatro casos opt-in `test_process_limits.py`/`test_client_streams.py` solo lanzan Python efímero local; su ejecución no acredita SSH o infraestructura. Evidencia de implementación en [docs/evidencia/009](../../docs/evidencia/009/).

## Pool de aplicaciones y publicación portable (convergencia 2026-10-25)

Para despliegues cotidianos, preparar en lote un pool de UUID/FQDN/IP/MAC/certificados en `network_profiles.instances` y en el registro root del runner, conforme a [conexion-infraestructura.md](../../docs/conexion-infraestructura.md). NAP consume una identidad aún no utilizada y fija su snapshot antes de crear; `net0` incluye su MAC de DHCP. No hay cambios por instancia en los perfiles ni administración general de DNS/CA. El agotamiento bloquea la creación y los reintentos no cambian identidad ni secretos. No reutilizar UUID históricos.

El antiguo `scripts.publicar_catalogo` específico de la PC ya no publica ni cambia cuentas. Ahora sólo comprueba un manifiesto completo y su evidencia externa mediante los argumentos `--manifest`, `--evidence`, `--cluster-uuid` y `--definition-id`. Informa coherencia local; el registro/validación/publicación sigue ocurriendo en la UI administrativa con las comprobaciones reales del backend. No completa checks ausentes ni selecciona automáticamente un administrador.
