# Guía de validación — feature 009

Esta guía prueba el diseño de [plan.md](plan.md) después de implementarlo. Hoy no están construidos los nuevos endpoints, worker, scripts, imágenes ni pruebas aquí propuestos. No ejecutar los ejemplos contra la base o contenedores de uso real. [Modelo](data-model.md) · [Auth](contracts/auth.md) · [Operaciones](contracts/operations.md) · [Catálogo/UI](contracts/catalog-ui.md) · [Runner](contracts/guest-runner.md) · [Evidencias](contracts/evidence.md) · [Revocación de consola](contracts/console-access.md).

## 1. Preparar entorno y evidencia

- Clon de trabajo, Python 3.12, Node >=22.12 de rama 22, Docker Compose y clientes PostgreSQL 16. Usar los locks generados durante implementación; no actualizar dependencias incidentalmente al validar.
- Base PostgreSQL de pruebas vacía y otra copia de actualización; doble Proxmox por defecto. Proxmox real se usa solo en fase explícita de integración con contenedores de prueba.
- Dos responsables con tres cátedras, administración, una cuenta con varias cátedras, una sin MFA y otra con MFA, más caso de único administrador en base aislada.
- Reloj controlable en pruebas para fechas, TOTP, reservas y quince minutos de alertas; no esperar semanas reales ni cambiar reloj del servidor operativo.
- Carpeta local de evidencia sin secretos: revisión Git, versiones, comandos/códigos de salida, casos, resultado esperado/observado, IDs anonimizados y limitaciones. Códigos, cookies, claves y cuerpos de acceso se redactan.

Antes de integración, infraestructura completa inventario: cluster_uuid, versiones PVE, arquitectura, nodos online, márgenes anfitrión, pools/storage rootdir/vztmpl, storage compartido/local, imágenes/digests, token/ACL, runner/hostkeys/recetas, perfil red, DHCP o direcciones existentes, DNS/TLS, red alumno, SMTP y destino/responsable de copias.

Un dato que falta bloquea habilitar ese destino. No se reemplaza por el host por defecto del repositorio. La consola requiere identidad PVE individual limitada a pools propios y demostrar revocación de permisos efectivos (también heredados) y terminación de sesiones ya abiertas, con prueba negativa mediante conexión previa y URL guardada. Sin esa capacidad demostrada no se habilita consola.

## 2. Comandos existentes y comandos que deben incorporarse

Desde la raíz del proyecto, estos comandos de comprobación ya existen:

~~~bash
git status --short
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
~~~

El backend debe ejecutarse desde backend para respetar su pytest.ini/PYTHONPATH. La forma recomendada para toda la suite es:

~~~bash
cd backend
./venv/bin/python -m pytest -q
~~~

Baseline del análisis del 18-10-2026: 320 pruebas pasan y una falla por expectativa antigua del límite de disco; frontend build/lint pasan con advertencias. Es evidencia previa, no una ejecución de este plan. Al cerrar implementación, actualizar esa prueba a la política vigente y exigir suite sin fallos.

Los siguientes comandos/interfases **se incorporan durante implementación**; no están disponibles todavía:

~~~bash
cd backend
./venv/bin/python -m scripts.preflight --entorno pruebas
./venv/bin/python -m scripts.validar_definicion --manifest /tmp/nap-validacion/manifest.json
./venv/bin/python -m pytest -q tests/postgres
./venv/bin/python -m scripts.validar_carga --servicios 100 --dias 90 --sesiones 10 --salida /tmp/nap-validacion/carga.json
~~~

~~~bash
npm --prefix frontend run test -- --run
npm --prefix frontend run test:e2e
npm --prefix frontend run test:performance -- --base-url https://nap-pruebas.example.edu --sesiones 10 --muestras-por-recorrido 100 --salida /tmp/nap-validacion/rendimiento-navegador.json
~~~

Desde la raíz, ejecutar también las suites de infraestructura con su configuración propia (se incorporan durante implementación):

~~~bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q infra/runner/tests infra/services/tests
~~~

`infra/pytest.ini` declara testpaths runner/tests services/tests y pythonpath .. ../backend; infra/conftest.py inyecta dobles y bloquea red/subprocess reales por defecto. backend/pytest.ini solo recolecta backend/tests: su ejecución no acredita estas suites. El job infra de CI y el cierre exigen recolectar y ejecutar al menos un test en **cada** suite; rutas faltantes o cero tests fallan, sin `|| true` ni omisión silenciosa. Las pruebas reales de PVE/imágenes no se ejecutan en ese job.

Los scripts de validación rechazan destinos ajenos al inventario de prueba y no crean datos en producción. CLI preflight y manifest solo leen/validan. La carga necesita generación de observaciones en base aislada y una API levantada con adaptador lento simulado. validar_carga exporta latencias HTTP y fixture/IDs para el ensayo del navegador; no acredita SC-008 por sí solo. test:performance usa SPA compilada servida por proxy de pruebas (no Vite dev server), API y PostgreSQL de ese mismo entorno, sin mocks de sus consultas. El dominio de ejemplo se sustituye por el destino aislado preparado. Los nombres propuestos quedan como interfaces a descomponer en tasks.md.

Para migraciones, desde backend, con DATABASE_URL apuntando explícitamente a una base vacía de prueba y después a una copia del esquema actual:

~~~bash
./venv/bin/alembic current
./venv/bin/alembic upgrade head
./venv/bin/alembic current
~~~

No instalar ni migrar la base real para probar el plan. Verificar fresh y upgrade, FKs/CHECK/índices, backfill e igualdad de esquema final; conservar cuentas/pedidos/servicios/historial del corte. Duplicados o fechas desconocidas deben generar diagnóstico/regularización, sin borrado ni fechas inventadas.

## 3. Autenticación y aislamiento — SC-001, SC-002, SC-015

1. Sin MFA: contraseña definitiva entra al portal sin inscripción. Cuenta provisoria solo accede a perfil mínimo, CSRF, cambio propio y logout; una llamada directa a pedidos/métricas devuelve 403.
2. Con MFA: contraseña emite exclusivamente mfa_pending; OTP correcto habilita la siguiente etapa. OTP inválido, desafío vencido/de otra sesión/reutilizado y replay del paso temporal no operan.
3. Iniciar/cancelar setup conserva estado anterior. Activar confirmado entrega diez códigos una sola vez. Recargar no activa un pendiente ni salta la etapa.
4. Contraseña+código admite solo recovery. Dos conexiones consumiendo el mismo código producen una sola recuperación. Confirmar nuevo factor invalida generación anterior. Disable exige pruebas explícitas y permite siguientes ingresos por contraseña.
5. Recuperación asistida del único admin: operador verifica identidad y usa CLI de auth.md, titular presenta contraseña+autorización; solo reconfigura factor, sin cuenta auxiliar.
6. Cinco fallos dentro de cualquier ventana móvil de quince minutos provocan espera; alternar cuentas desde un origen también se limita. Incluir cuatro fallos antes y después de un límite de reloj para detectar buckets eludibles.
7. Cookie HttpOnly/Secure y CSRF: sin Origin/cabecera/CSRF válido, mutaciones rechazadas; token no aparece en Web Storage. Logout y rotación invalidan sid antiguo.
8. Responsable A no consulta/cambia pedidos, servicios, acceso, última métrica o historia de B. Docente no cancela/reenvía ni su pedido propio ni uno ajeno; admin sí realiza esas decisiones con motivo/historial y campos válidos.
9. Mantener consola PVE abierta y URL guardada. Solicitar reasignación/retirada/desactivación/cambio de rol: 202 y bloqueo NAP afectado, trámite pendiente y sin acceso del nuevo titular. Operador revoca permisos efectivos y termina sesiones; importa evidencia y admin confirma. Probar conexión previa/URL denegadas y otros pools legítimos accesibles con sesión nueva; ahora la siguiente petición usa titularidad efectiva. Fallo externo mantiene trámite pendiente/fallido sin transferencia ni mensaje de éxito. Probar también inventario nativo desconocido, reinicio, replay y revisión concurrente.
10. Dos degradaciones/retiros simultáneos, contando trámites pendientes al admitir y revalidando al completar, nunca bloquean a todos los administradores. La simulación del protocolo no sustituye el ensayo nativo real de consola.

Reproducir desde navegador y HTTP directo respetando cookies/Origin/CSRF; no inyectar un JWT privilegiado como sustituto de probar login. Para aislamiento se puede usar fixture operativa, pero conservar prueba real del ingreso.

## 4. Capacidad y recuperación — SC-003, SC-004

Ejecutar en PostgreSQL 16 con dos sesiones independientes y una barrera que haga simultánea la decisión. Repetir diez veces: dos aprobaciones para saldo de una, doble aprobación del mismo pedido, dos start/reactivar, approve/reversión/expiry y renovación/vencimiento.

Comprobar:

- Un solo compromiso e historial de decisión; perdedor recibe 409 explicativo, sin estado parcial. El token liga la selección real y editar recursos exige reevaluar.
- Reserva se cuenta en APROBADO, EN_DESPLIEGUE y resultado incierto; recurso propio materializado no se suma otra vez. QEMU externos y storage compartido forman parte del inventario aunque no se ofrezcan QEMU nuevos.
- Storage root de nodo no se usa como pool LXC; espacio libre físico no descuenta otra vez discos existentes. Destino insuficiente bloquea aunque el total agregado alcance.
- Start/reactivar usa misma admisión/vigencia. Sin cómputo mantiene pausa y datos. Sobreasignación solo admin con cifras/motivo.
- config_extra/opciones no cambian VMID, nodo, recursos, unprivileged, montajes, storage ni aislamiento.

Para crear/iniciar/pausar/eliminar, el doble simula tarea aceptada y luego fallo, timeout o éxito tardío. Interrumpir antes de enviar, entre dispatch y UPID, entre recurso creado y commit, y durante lease vencido. Reiniciar worker:

- 202 no se presenta como éxito final.
- Reconcilia recurso/marca/nonce antes de repetir. No adopta/elimina uno ajeno con igual hostname/VMID.
- Pausa/baja fallida no libera capacidad que sigue ocupada.
- Propietario viejo no confirma ni elimina lock del nuevo.
- Sin efecto confirmado libera lo permitido; con incertidumbre conserva identidad/compromiso y ofrece diagnóstico.
- Repetir Idempotency-Key devuelve la decisión original; cambiar payload produce 409. Probar también creación de pedidos, calendarios y aprobación de renovación sin operación PVE.

## 5. Calendario, pedidos y períodos — SC-006, SC-014, SC-016

Como docente crear/consultar pedido y observaciones; como admin corregir/reenviar/cancelar. Verificar controles ocultos al docente y 403 HTTP aun sobre su propio pedido. Configurar dos años con primer/segundo cuatrimestre/anual y conservar opción personalizada. Probar calendario ausente/incompleto, año distinto, cambio de modalidad, fechas invertidas, fin vencido y día final completo en zona institucional.

Aprobar alta para dentro de varias semanas: reserva retenida desde ahora y expiración min(fin, max(aprobación,inicio)+24h). A las veinticuatro horas desde aprobación anticipada no caduca; antes de inicio no crea/enciende, al inicio se habilita acción, después de fin no activa. Cambiar calendario no modifica el snapshot aprobado.

Crear servicio con dato y renovación posterior separada. Al terminar el primer período, detener y confirmar pausa aunque renovación esté pendiente/aprobada. No encender durante el receso; conservar disco/identidad/datos. Al nuevo inicio probar éxito con capacidad y 409 sin capacidad, permitiendo reintento. Períodos contiguos no causan un corte innecesario.

Modificar fechas aprobadas mediante nueva decisión trazable, nunca PATCH directo de vence_at. Verificar sustitución del período sin eliminar historia y reevaluación de capacidad si cambia una alta aún reservada.

## 6. Preparación y catálogo real — SC-005, SC-013, SC-017

Esta fase necesita infraestructura coordinada. Cada receta tiene build reproducible, versiones exactas, imagen/receta digest, prueba de saneamiento y registro permitido en runner. La preparación inicial se hace en entorno aislado; la publicación satisface [schema](contracts/service-definition.schema.json), no un manifiesto ficticio.

1. Preparar Linux Ubuntu 24.04, PostgreSQL 16 y BookStack 26.09.1 con dependencias fijadas. No conservar usuarios de cliente, claves o contraseñas de imagen. Linux entrega cuenta propia del invitado para la consola.
2. Verificar runner sin shell libre/forwarding, hostkey fija, rechazo de otra cátedra, digest distinto y comandos/rutas libres. Cortar transporte durante bootstrap y repetir sin reinicializar datos/claves.
3. Crear borrador de definición; el builder produce JSON validacion_definicion con dos instancias de laboratorio, checks/digests y operador. Admin importa con POST /evidencias, recibe UUID/checksum y los copia a validation.evidence_id/evidence_sha256 del manifiesto según evidence.md. Validar el manifiesto y publicar versiones y perfiles de recursos. Solicitar/aprobar/desplegar dos instancias de cada aplicación desde NAP sin instalar paquetes ni editar código por instancia.
4. Confirmar tarea, bootstrap, IP/FQDN/TLS reales y función. Administración revela el acceso inicial preparado en modo solo_validacion para realizar la prueba desde red alumno y prepara/importa JSON acceso_instancia mediante POST /evidencias y usa el UUID devuelto en POST /servicios/{id}/verificar-acceso, con endpoint/instante idénticos. El documento incluye servicio/definición/resource_uuid/nonce_sha256/preparacion_id, origen/equipo/red y pruebas satisfactorias; backend contrasta preparación vigente e identidad. Probar UUID inexistente, JSON alterado, tipo erróneo, instancia anterior, resultados incompletos y simulación: no habilitan acceso real. Antes de ella el portal no declara utilizable el servicio ni entrega acceso ordinario a cátedra. La comprobación local del runner no la sustituye.
5. PostgreSQL: cuenta propia, CREATE/INSERT/SELECT, dato persiste tras detener/iniciar; no acceso cruzado ni a base interna NAP.
6. BookStack: docente crea libro/página con imagen/adjunto y dos lectores individuales. Ambos leen, ninguno edita/gestiona usuarios; credenciales no sirven en otra instancia. Revocar uno bloquea su siguiente acceso sin afectar al otro. Probar acceso a imagen/adjunto sin sesión: denegado. Reiniciar preserva contenido/cuentas/permisos.
7. Linux: abrir solo consola del contenedor propio con ACL/pool y autenticar cuenta guest; no visibilidad del clúster. Estado running sin login utilizable no completa IaaS.
8. Editar/retirar template/definición conserva servicios e historial; nueva solicitud no usa retirada. Aprobación previa conserva snapshot y artefacto sin cambio silencioso.

BookStack es una referencia provisional. Registrar preguntas pendientes del producto del cliente sin tratarlas como incumplimiento del catálogo básico delegado.

## 7. Observación y experiencia — SC-007–SC-010

- Repetir GET desde diez visitantes no produce más capturas. Manual y scheduler comparten deduplicación de minuto.
- Contadores constantes no generan actividad falsa; reset o hueco no genera tráfico negativo. Muchas capturas juntas no reemplazan intervalos perdidos. Sin cobertura no pausar por inactividad.
- Dos negativos separados un minuto abren caída; CPU/RAM >90 % durante quince minutos confirmados abren incidente; dos normales lo resuelven. Por incidente hay una apertura/recuperación, sin correos nuevos en cada revisión.
- SMTP lento/fallido conserva evento/decisión y muestra error admin; reintento no duplica aviso lógico. Probar texto de bienvenida sin secretos en logs, incluso mock.
- Agregar detalle >90 días antes de purgar. Consultar consumo por cátedra/período tras cambio de titular/baja; resúmenes conservan cobertura y asignación, no promedios engañosos.
- SC-008 requiere el protocolo de navegador descrito abajo: datos completos, diez sesiones, despliegue lento y p95 de resultado visible por recorrido <=3 s. El p95 HTTP se conserva como diagnóstico separado.
- Teclado: solicitud, aprobación, seguridad, métricas, acceso y diálogos; foco visible/inicial/retorno, fondo inerte y alternativa textual de gráficas. Clipboard denegado informa resultado real.
- Responsable de una cátedra de prueba: completa pedido/consulta sin ayuda en <=3 minutos, excluida decisión/espera externa. Si falla el objetivo, registrar problema y corregir antes de aceptación.

### Protocolo reproducible de SC-008

1. Sembrar exactamente cien servicios con detalle de noventa días a un minuto (12,96M muestras), fechas distribuidas y datos conocidos por recorrido en PostgreSQL aislado; registrar revisión/locks, tamaño, índices/EXPLAIN, versiones y recursos DB/API/worker/proxy/navegador, red y equipo generador. No purgar los datos del ensayo antes de medir.
2. Compilar y servir SPA con proxy de pruebas. Abrir diez contextos de navegador autenticados con cookies independientes (cinco docentes con datos autorizados y cinco admins). Iniciar un despliegue con doble de PVE que permanezca pendiente durante toda la ventana medida, mínimo treinta segundos, conservando 202/operación real del backend. Verificar que sigue abierto durante las muestras y confirmar al terminar. No simular respuestas de listados/métricas.
3. Medir tres recorridos por separado: abrir listado de pedidos con un filtro conocido (`GET /pedidos/`); cambiar filtro de modelo del listado de servicios (`GET /servicios/`); abrir métricas de un servicio/rango conocido (consultas de métricas/resumen del contrato). La vista resultante debe contener los datos esperados de la consulta actual: no alcanza que haya una fila vieja o un spinner oculto. Alternar filtros/rangos con resultados conocidos, manteniendo reparto de usuarios fijo y tareas escalonadas para sostener diez sesiones activas.
4. Realizar cinco consultas de calentamiento por contexto y recorrido y excluirlas explícitamente. Después medir al menos cien muestras por recorrido, distribuidas equitativamente entre los diez contextos. En cada muestra iniciar marca en captura del evento de navegación/clic/filtro; terminar después del pintado del resultado actual, con aria-busy desactivado y filas o gráfica **y** alternativa textual correctas/visibles y controles utilizables. Incluye cliente, solicitud, transferencia y renderizado. Usar el reloj monotónico del navegador, evitando sumar o comparar relojes servidor/cliente. Sesión/login y generación de datos se preparan antes y no se miden.
5. Conservar caché normal de recursos estáticos tras calentamiento; desactivar cache HTTP de datos para el ensayo y alternar claves de consulta conocidas para exigir consultas reales. Documentar navegador/viewport y política de caché/red. Timeout de treinta segundos por muestra. Cada error, dato incorrecto, falso vacío o timeout se registra y cuenta como incumplimiento, sin descartarlo ni medirlo como respuesta rápida exitosa.
6. Exportar muestra por muestra: recorrido/contexto, inicio, duración, resultado válido/error/timeout, clave de consulta y operación lenta en curso; sin cookies/secretos. Calcular p95 nearest-rank por recorrido sobre todas las duraciones y, además, proporción de muestras con resultado válido en <=3000ms sobre **todas** las muestras del recorrido. Exigir p95 <=3000ms y proporción >=95% en cada uno de los tres recorridos, sin compensar uno lento con otro rápido. Adjuntar resultados HTTP/DB como diagnóstico independiente y conservar fallos explícitos.

Las acciones de crear/encender/esperar infraestructura no son consultas ordinarias de este umbral; el listado y seguimiento del recurso sí deben seguir responsivos. El registro del ensayo se guarda en docs/evidencia/009/rendimiento-navegador.json y se enlaza en aceptación. Un build exitoso o benchmark HTTP aislado no acredita SC-008.

## 8. Respaldo, actualización y reinicio — SC-011, SC-012

Política inicial externa: diario, siete diarios/cuatro semanales, cifrado y copia fuera del nodo, más copia previa a cambios incompatibles. Infraestructura documenta destino y operador. RPO de hasta veinticuatro horas depende de copia exitosa; medir RTO en ensayo.

Clientes PostgreSQL utilizan servicio de conexión/archivo de credenciales privado; no poner contraseñas en comandos o repositorio. Ejemplo de herramientas existentes, hacia archivos nuevos de prueba:

~~~bash
PGSERVICE=nap_backup pg_dump -Fc -f /tmp/nap-validacion/portal.dump
PGSERVICE=nap_restore pg_restore --exit-on-error --single-transaction -d nap_restore /tmp/nap-validacion/portal.dump
~~~

nap_restore debe apuntar a una base aislada preparada; el nombre anterior no corresponde a la base operativa. Conservar también roles/configuración requeridos y keyring separado. Restaurar datos sin claves no acredita recuperación de secretos.

Portal restaurado: antes de habilitar acceso, revocar sesiones/desafíos y códigos de recuperación del corte para no reactivar credenciales consumidas después. Conservar factores activos; tras contraseña+TOTP emitir juego nuevo o usar asistencia si se perdió el factor. No reanudar outbox/operaciones restauradas contra infraestructura hasta reconciliar, ni reenviar bienvenidas con secretos antiguos.

PostgreSQL PaaS: recuperar dato de referencia, rol y acceso en instancia separada. BookStack: recuperar corte consistente MariaDB + .env/APP_KEY + imágenes/adjuntos/temas; misma versión inicial, cuentas/permisos y lectura comprobadas. No tratar restore como bootstrap que genere claves nuevas.

Reiniciar API/worker no crea cuentas demo, resetea claves ni pierde decisiones confirmadas. Configuración productiva inválida debe fallar preflight sin imprimir secretos. Desde otra computadora verificar SPA/API/servicios con DNS/TLS y origen real; localhost del visitante no es dirección del servidor.

## 9. Registro de aceptación

| Evidencia | Criterios |
|---|---|
| Permisos, sesión, MFA/códigos y carreras de administración | SC-001, SC-002, SC-015 |
| Concurrencia de capacidad y recuperación de tareas | SC-003, SC-004 |
| Dos aplicaciones de cada tipo y lectores individuales | SC-005, SC-013, SC-017 |
| Fechas, reservas futuras y renovación con receso | SC-006, SC-014, SC-016 |
| Prueba con personas, carga, incidentes y teclado | SC-007, SC-008, SC-009, SC-010 |
| Fresh/upgrade, restauración y documentación | SC-011, SC-012 |

Actualizar informe técnico, manual docente, manual administrador, modelo de datos, instalación/operación e inventario. Matriz de objetivos/hallazgos enlaza pruebas y evidencia; separar trabajo individual e infraestructura y registrar integraciones postergadas. Una prueba simulada nunca marca como aprobada una integración real pendiente.
