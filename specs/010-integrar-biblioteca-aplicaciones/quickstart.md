# Guía de validación: biblioteca y Draw.io

Esta guía se ejecuta después de implementar las tareas de 010. Hoy describe resultados esperados: no acredita endpoints, imagen ni ensayos realizados. Los comandos de suites existentes son utilizables en el checkout; los casos nuevos deben agregarse durante implementación y no pueden darse por cubiertos por pasar sólo pruebas anteriores.

## 1. Prerrequisitos

- Python 3.12, entorno `backend/venv` con dependencias del lock del proyecto; Node y dependencias frontend conforme a archivos lock.
- Configuración de pruebas según `backend/README.md`, sin credenciales operativas. PostgreSQL 16 de prueba independiente; la suite exige usuario `nap_test`, base `nap_test_*` y host local o `postgres_test`.
- Para aceptación real: entorno staging separado; rol administrador y dos responsables de cátedras distintas; pools docente/ensayo, al menos dos LXC temporales, CPU/RAM/disco y espacio institucional para artefactos; base Ubuntu verificada y receta comprometida; builder y runner con hostkeys y registros permitidos.
- Dos identidades de ensayo y dos de entrega con FQDN/IP/MAC/certificados institucionales; ningún UUID ni credencial compartidos. Fecha institucional y vigencias válidas desde 2026.
- Habilitar adaptador Community Scripts de sólo lectura y registro de artefactos propuestos en [contrato](contracts/preparacion-runner.md). No pegar comandos de proveedor en la consola PVE.

## 2. Validación automatizada local

Desde la raíz del repositorio, instalar dependencias frontend si faltan:

```bash
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test -- --run
npm --prefix frontend run test:e2e
```

Las pruebas de navegador locales usan mocks y no acreditan conectividad PVE ni la aplicación real. Deben incluir el flujo biblioteca, acceso por teclado, conservación de datos tras errores, oferta preseleccionada y cambio de versión.

Desde `backend/`, ejecutar contratos/dobles y regresión existente sin PostgreSQL:

```bash
./venv/bin/python -m pytest -q tests --ignore=tests/postgres
```

Desde la raíz, ejecutar suites de infraestructura; añadir los tests del builder nuevo en la misma ejecución cuando existan:

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests infra/laboratorio/tests
```

La implementación agregará `infra/builder/tests` y lo incluirá en configuración de pruebas/CI; debe recolectar y ejecutar casos reales, sin omitir la carpeta faltante ni aceptar cero pruebas. No usar una ejecución de backend como evidencia de estas suites.

Para PostgreSQL, iniciar exclusivamente el servicio de pruebas existente:

```bash
docker compose -f docker-compose.test.yml up -d --wait postgres_test
```

En una terminal desde `backend/`, con configuración de aplicación de pruebas ya preparada:

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://nap_test:nap_test_local_only@127.0.0.1:55432/nap_test_009'
./venv/bin/python -m pytest --require-postgres -q tests/postgres
```

La base `nap_test_009` es la creada por el compose actual; el nombre no impide probar 010. Cada fixture crea/elimina su esquema aleatorio y la guarda rechaza bases operativas. Si se cambia `NAP_TEST_PORT`, ajustar el puerto de la URL. Probar migraciones 010 sobre una copia aislada de esquema/datos 009; nunca contra el portal en uso. Al terminar:

```bash
docker compose -f docker-compose.test.yml down
```

## 3. Casos automáticos exigidos

| Caso | Resultado esperado |
|---|---|
| Búsqueda con tres alias, categoría y datos desconocidos | Draw.io localizado; origen de datos explícito, sin inventar versión |
| Búsqueda vacía, timeout, 429 y árbol truncado | Distinguir sin resultados/fallo/cache, límites y reintento; nunca ejecutar shell |
| Incorporación repetida con misma u otra clave | Mismo borrador para misma identidad/version, sin perder edición |
| Otro producto encontrado | Importable como ficha, no instalable/publicable sin adaptador |
| Ensayo sin builder/red o sin capacidad | Rechazo sin contenedores ni reservas huérfanas |
| Dos admisiones simultáneas: ensayo vs aprobación | Ledger y lock comunes impiden sobrecompromiso accidental |
| Build confirmado con entradas exactas | Descargas/paquetes fijados, imagen y bundle verificados; ninguna publicación automática |
| Confirmación de builder/PVE perdida | Reconciliar mismo trabajo/UUID/UPID, sin segundo recurso |
| Artefacto con secreto/estado del ensayo | Saneamiento/publicación fallan; ninguna oferta docente |
| Borrador, evidencia fallida o réplica faltante | Publicación rechazada con motivo |
| Ensayo vence durante build/crear/bootstrap | Fencing impide resurrección; limpieza pendiente durable |
| Limpieza falla o elimina sólo un recurso | Capacidad restante retenida; reintento seguro, evidencia/imagen conservadas |
| Dos workers y lease vencido | Worker antiguo no confirma, publica ni vuelve a crear |
| Publicar nueva versión entre evaluación y aprobación | 409 y nueva evaluación administrativa; sin confirmación docente |
| Actualización antes/después de aprobar | Antes usa vigente y avisa; después conserva snapshot original |
| Retirar mientras docente completa pedido | Datos conservados, selección a revisar; aprobados mantienen referencia |
| Renovación y «Otro» | Renovación conserva versión; «Otro» conserva descripción y vincula oferta por decisión |
| Manifiestos/evidencia 009 | Siguen válidos; no se abren productos/parametros libres |

La nueva suite debe usar dobles que hagan fallar llamadas no previstas; guardar fixtures públicos de la fuente con revisión, sin depender de Internet durante CI.

## 4. Ensayo real y publicación — US1/US2

1. Entrar como administrador en Definiciones. Buscar `drawio`, `draw.io` y `diagramas`. Medir el tiempo desde buscar hasta incorporar (<2 min con proveedor disponible). Confirmar que sólo se incorporó una ficha, con comando/origen y faltantes; no se creó un LXC.
2. Editar datos administrativos y volver a incorporar: mismo borrador, sin sobrescribir la edición. Completar Draw.io y elegir código/versión NAP; diferenciarla de la versión externa.
3. Iniciar preparación desde NAP. Ver plazo/vencimiento, capacidad de dos recursos y estado consultable. Revisar resolución con versiones exactas, hashes y revisión de receta; confirmar entradas. No ejecutar manualmente el comando externo.
4. Esperar imagen/bundle y dos LXC creados desde el mismo paquete. Recargar navegador durante el trabajo: conserva estado, recursos e historial. Repetir envío/pérdida de confirmación en entorno controlado: no duplica.
5. Revelar acceso de ensayo mediante acción auditada. Desde la red prevista, crear diagrama con texto identificable, editarlo, exportar archivo editable `.drawio` y reabrirlo conservando nodos/contenido. Registrar hash del archivo y resultados. Reiniciar y repetir acceso/edición; los archivos permanecen en el equipo del usuario, no en un almacenamiento central prometido.
6. Probar instancia B con credenciales de A y acceso anónimo: denegados. Verificar puerto Tomcat inaccesible desde la red cliente y TLS válido. Inspeccionar artefacto limpio para ausencia de contraseñas/diagramas/identidades/TLS de ensayo. Conservar evidencia de saneamiento y de despliegue repetible de ambas instancias.
7. Importar evidencia real por el mecanismo institucional; vincular a ensayo/definición/digests, validar y publicar la oferta con su perfil. Antes de comprobar, un intento de publicar debe fallar. Registrar usuario y fecha de cada decisión.
8. Verificar limpieza automática de los dos LXC, presupuesto temporal liberado y registro de ausencia. La imagen final, el bundle, las evidencias y la oferta siguen disponibles; sus bytes retenidos siguen ocupando almacenamiento.
9. En un ensayo separado, descartar y luego probar vencimiento con reloj de prueba/TTL mínimo admitido; registrar aviso previo. Simular fallo de eliminación, comprobar capacidad retenida y reintentar hasta confirmar ausencia. No cambiar el reloj del nodo productivo.

## 5. Entrega a dos cátedras — US3

1. Responsable A solicita Draw.io desde Catálogo: selección conservada. Responsable B lo elige desde Nuevo pedido → Software. Completar cátedra, nombre, justificación y fechas, sin hardware, en <3 min por recorrido. «Otro» sigue disponible.
2. Mantener una alta pendiente, publicar una segunda versión comprobada sobre el mismo perfil y evaluar/aprobar. Debe usar versión vigente, reservar sus requisitos, conservar la solicitada y registrar/avisar diferencia sin confirmación docente. Publicar otra versión después de aprobar no cambia el snapshot.
3. Administrador aprueba con evaluación vigente y despliega desde fecha inicial. Ambas instancias tienen identidad, pool/red, credenciales y acceso propios. Una fecha futura no crea anticipadamente recursos; no hay autoaprobación.
4. Cumplir comprobación externa por servicio antes de activación/revelado al responsable, como en el flujo vigente. En ambas instancias repetir ciclo editable; consultar/operar recurso de B como A devuelve denegación. Credencial HTTPS de A no sirve en B.
5. Bloquear acceso a Community Scripts/GitHub del proveedor en un entorno controlado después de publicar (sin bloquear almacenamiento institucional). Confirmar falla/aviso de búsqueda y catálogo interno disponible. Crear, aprobar y desplegar un tercer pedido nuevo desde la versión preparada; comprobar el editor. Inspeccionar tráfico/logs: ninguna consulta/descarga a Community Scripts durante despliegue ni bootstrap. El ensayo no prueba que todas las funciones cloud de Draw.io funcionen offline.

## 6. Evidencia y cierre

Guardar resultados reales en `docs/evidencia/010/` durante implementación: revisión de código/configuración, versiones PVE/runtime, artefactos/digests, dos identidades, origen/red/equipo de pruebas, operador/fecha, archivos editables y comprobaciones, carreras/fallos/limpieza, mediciones SC-001/004 y latencia técnica. No guardar contraseñas, headers de autorización ni claves privadas.

La evidencia sintética sólo acredita tests. El gate real permanece pendiente hasta comprobar saneamiento, red institucional, ciclo editable, aislamiento y despliegue sin proveedor. No publicar como oferta comprobada por haber pasado únicamente build/CI.
