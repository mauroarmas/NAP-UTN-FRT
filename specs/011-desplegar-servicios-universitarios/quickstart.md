# Quickstart de validación — después de implementar 011

Este documento es una guía de ejecución y aceptación, no una implementación ni un reporte de
pruebas realizadas. Los módulos y fixtures nuevos indicados deben ser creados por las tareas.
No ejecutar instalación sobre un nodo compartido sin la preparación y destinos controlados.

## 1. Preparación técnica, una vez

- Branch `011-desplegar-servicios-universitarios`; instalar dependencias bloqueadas del proyecto.
  Portal en su entorno habitual; no copiar `.env`, tokens, claves o identidades del laboratorio a
  otro clúster. Para la aceptación usar cátedras y datos de ensayo identificables.
- Respaldar la base antes de la migración; probar upgrade desde `010_06_acceso_aplicacion` en una
  copia aislada, conservando usuarios, cátedras, pedidos, servicios y artefactos Draw.io.
- Preparar bases verificadas Ubuntu 24.04/runtime Docker y Debian 13/Core; fuentes/versiones/hashes,
  permisos del runner cerrado, systemd, espacio y cuentas dedicadas. No ampliar token a root.
- Configurar slots nuevos de red disjuntos, DNS/TLS, firewall y clientes autorizados; validar
  conectividad del mecanismo de acceso. Las credenciales no van en el repositorio o consola.
- Preparar un registry de laboratorio accesible con TLS y, para el ensayo privado, acceso de lectura
  limitado. Los perfiles privados se registran por infraestructura, no por cada administrador.
- Mantener perfiles `pendiente_validacion` hasta completar el siguiente gate. Esta preparación
  no significa que la universidad tenga configurado su clúster/red.

La tarea de bootstrap de `infra/laboratorio/011/preparar_entorno.py` se ejecuta después del
preflight y antes de los spikes. Prepara prerrequisitos y candidatos, no instala paquetes de NAP
que todavía no estén construidos. La instalación del runner común y de cada estrategia definitiva
se realiza al terminar sus tareas de construcción, antes de la validación real de ese perfil;
el cierre documental sólo revisa la guía/rollback, no posterga esta preparación al final.

Referencias: [configuración](contracts/configuracion.md), [runner](contracts/runner.md),
[modelo](data-model.md), [fuentes y decisiones](research.md).

## 2. Gate de factibilidad real antes de habilitar perfiles

Usar exclusivamente invitados de ensayo con propiedad NAP comprobada. El responsable técnico
verifica y registra resultados sin pegar credenciales:

1. Docker dentro del LXC no privilegiado: features exactas mediante wrapper cerrado, AppArmor y
   seccomp activos, storage soportado, acceso a paquetes/registry, recursos completos <=Medium.
   Probar pull público y privado y comprobar que no queda login del registry al iniciar la app.
2. Harness Community: loader local y revisiones correctos, OS compatible, paquetes/releases
   bloqueados, stdin sin preguntas, sin modificaciones del host, telemetría/trazas/autologin
   desactivados. Verificar que Core no guarda stdout o comandos con secretos en `.log`/`.errinfo`.
3. Aislamiento de red: guest no accede al nodo, API/base del portal ni otra cátedra; sólo destinos
   de instalación y clientes/gateway admitidos. Probar desde fuera del guest; UFW solo no basta.
4. Productor seguro/systemd: corte de SSH y salida de worker no detienen una ejecución autorizada;
   ningún dato sensible aparece en spool/journal/DB. Un reboot sin resultado queda incierto.
5. Perfil MariaDB y perfil Caddy completan instalación/acceso propios con sus respuestas fijadas.
   Si falla por permisos, recursos o dependencia no admitida, dejar bloqueado y registrar motivo.
   No convertir a privilegiado, desactivar protecciones, usar el wrapper host o subir de tamaño.

El gate real y sus impedimentos van al reporte del laboratorio. Las fakes validan contratos, no
habilitan un perfil ni certifican el despliegue en otro nodo.

## 3. Comprobaciones automatizadas

Desde la raíz del repositorio. Los nombres nuevos de pruebas son los previstos por este diseño;
si todavía no existen, la implementación no está lista para ejecutar la aceptación.

```bash
backend/venv/bin/pytest -q \
  backend/tests/test_configuracion_despliegue_011.py \
  backend/tests/test_orquestacion_aplicaciones_011.py \
  backend/tests/test_consola_operacion_011.py \
  backend/tests/test_despliegue_programado_011.py
```

Esperado: ambos orígenes, fuentes incorrectas/SSRF, perfiles bloqueados, pérdida de respuesta,
reconciliación sin duplicados, permisos/secretos, datos persistentes y programación respetados.

PostgreSQL aislado (credencial siguiente es únicamente la pública de la fixture local de pruebas):

```bash
docker compose -f docker-compose.test.yml up -d --wait
TEST_DATABASE_URL=postgresql+asyncpg://nap_test:nap_test_local_only@127.0.0.1:55432/nap_test_009 \
  backend/venv/bin/pytest --require-postgres -q \
  backend/tests/postgres/test_despliegue_011.py \
  backend/tests/postgres/test_consola_011.py \
  backend/tests/postgres/test_migracion_011.py
docker compose -f docker-compose.test.yml down
```

Esperado: dos aprobaciones/takeovers/ingestas concurrentes no duplican recurso, compromiso,
execution_id o fragmento; migración preserva filas y esquemas históricos. No usar SQLite para
dar por acreditada esa concurrencia ni reutilizar el DSN de la base operativa.

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
cd frontend
npx playwright test tests/e2e/despliegue-aplicaciones.spec.js
```

Esperado: UI de ambos orígenes, consola de lectura negra/blanca, reconexión, scroll, permisos,
copy/export, contenido literal y estados reales. E2E con backends simulados se identifica como tal.
Las pruebas unitarias del paquete `infra/applications/tests/` también cubren el harness, protocolos,
redacción por chunks y recuperación de systemd sin usar un Proxmox real.

## 4. Fixtures para demostrar un motor común

- **Community**: MariaDB y Caddy con perfiles fijados en [research.md](research.md), Medium inicial.
- **Imagen propia**: fixture `infra/applications/fixtures/campus-demo/`, aplicación de prueba con
  página, endpoint de salud y escritura/lectura de un dato en volumen. Es software de ensayo que
  representa un proyecto de cátedra; construir/publicar la imagen es labor del desarrollador,
  no una función de build agregada al portal.
- **Otra imagen**: `traefik/whoami:v1.11.0`, servidor HTTP pequeño de
  [su proyecto oficial](https://github.com/traefik/whoami). Resolver y fijar digest de plataforma
  antes de aceptar el ensayo; su respuesta no debe contener cookies ni credenciales NAP.

Para construir la fixture propia, sólo cuando exista y se haya preparado un registry de ensayo:

```bash
docker build -t "${NAP011_TEST_REGISTRY:?Configurar registry de ensayo}/nap/campus-demo:acceptance" \
  infra/applications/fixtures/campus-demo
docker push "${NAP011_TEST_REGISTRY:?}/nap/campus-demo:acceptance"
```

La variable contiene host del registry, nunca usuario/contraseña. Autenticación y CA se preparan
mediante archivos privados. No publicar imágenes, datos o credenciales de la universidad en un
registry público para completar la prueba.

## 5. Recorrido funcional del administrador y la cátedra

Para cada origen, con datos de ensayo y los perfiles realmente habilitados:

1. Administración entra en Catálogo → Agregar servicio. Elegir biblioteca o imagen propia;
   completar datos necesarios y agregar. Cronometrar interacción <=3 min, excluyendo esperas de
   instalación externa que todavía no ocurre. No aparecen JSON, hashes, entorno de ensayo o
   botones de preparar/publicar. PVE no contiene nuevos CT ni la capacidad tiene nuevas reservas.
2. Una cátedra elige la oferta, escribe propósito y fechas y envía (<=2 min de interacción).
   Repetir con «Otro» aportando opcionalmente referencia de software propio.
3. Administración evalúa/aprueba con tamaño admitido y solicita despliegue. Comprobar reserva,
   snapshot de revisión/imagen y transición central. Con fecha futura sólo queda programado.
4. Abrir Ver consola durante la instalación: fondo negro/blanco, etapas reales, mensajes seguros,
   sin input. Cerrar ventana y volver: mismo intento efectivo/recursos, sin reinicio de instalación.
5. Confirmada la disponibilidad, pedido Activo y aviso del portal; abrir la aplicación por Servicios.
   MariaDB permite conexión autenticada TLS y `SELECT 1`; Caddy sirve su página a través de NAP.
   Las imágenes permiten abrir su página y la demo propia conservar/escribir su dato.
6. Con otra cátedra solicitar la misma oferta: recurso, acceso y datos distintos. Detener/reiniciar
   la primera conserva sus datos y no afecta a la segunda. Ejecutar secuencialmente otros ensayos
   si la capacidad no permite sostener todas las aplicaciones a la vez.
7. Retirar oferta: impide nuevos pedidos, mantiene instancias. Eliminar una instancia propia con
   confirmación de datos destructiva y comprobar ausencia antes de liberar capacidad y slot de red.
8. Repetir consulta/operación como cuenta ajena y cátedra: sin consola técnica ni datos de otros.
   Cambiar titular/rol o cerrar sesión y comprobar rechazo de nuevas lecturas/exportaciones.

## 6. Recuperación y fallos obligatorios

- Perder respuesta de `start` después de arrancar unidad; cortar worker/SSH, recuperar lease y
  verificar misma ejecución. Cambiar node_boot_id deja estado incierto hasta reconciliación.
- Fallar la creación del CT antes de start: consola con hitos/error seguro del portal aunque
  no exista job; reobservar el hito no lo duplica. Mezclar un evento portal y un fragmento runner
  con la misma clave local no produce colisión; sólo el fragmento runner avanza su ACK.
- Doble clic y dos consumidores: no duplicación. Un fallo confirmado permite nuevo intento
  enlazado, sin resetear el historial; incertidumbre no permite repetir ciegamente instalación.
- Recrear tras ausencia confirmada mantiene valores/referencias de secretos de aplicación del
  mismo pedido y renueva UUID/nonce/claves TLS de infraestructura. Un nuevo pedido de alta recibe secretos
  de aplicación distintos y nunca hereda los del ocupante anterior de un slot de red.
- Cambiar tag tras aprobar: se usa digest congelado. Digest/script/paquete inaccesible: fallo
  explícito, nunca otra versión. Imagen incompatible/privilegios excesivos: no oferta habilitada.
- Simular DB caída, disco lleno, instalación que pide entrada y fallo de eliminación: ningún raw
  log, éxito falso o liberación de recurso cuya ausencia no está confirmada.
- Emitir tokens/contraseñas conocidos y generados declarados partidos en cada frontera de chunk,
  una salida desconocida y escapes de terminal/página: ninguna fuga en spool, journal, DB,
  pantalla, copia o descarga; la salida desconocida se suprime con aviso seguro.
- Más de 10 000 000 bytes entre varios intentos y vencimiento de 30 días: recorte/vencimiento
  visibles, resultado/historia conservados. Exportar con snapshot mientras hay mensajes nuevos.
- Agenda futura con reloj controlado, revisión reemplazada y reserva: nunca CT anticipado,
  duplicación por tick ni caducidad previa al inicio programado; autor sistema identificable.

## 7. Evidencia mínima y cierre

Conservar reporte de fechas, versiones efectivas, perfiles, cuatro aplicaciones probadas,
comprobaciones realizadas y resultados de fallos. Sin contraseñas ni dumps de configuración privada.
Instrumentar dos instalaciones y verificar p95 captura→pantalla <=5 s y lectura inicial <=3 s con
registro retenido lleno. Comprobar usuarios/cátedras y servicios previos intactos, incluyendo acceso
Draw.io e IaaS, sin recrearlos para la prueba.

Marcar cada resultado como automatizado/simulado, laboratorio real o pendiente institucional.
Un fallo real bloquea el perfil concreto. Cerrar la aceptación sólo cuando las verificaciones
exigidas por la spec estén demostradas, no por la existencia de estas instrucciones.
