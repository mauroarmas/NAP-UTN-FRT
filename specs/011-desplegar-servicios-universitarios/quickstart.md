# Quickstart de validación — Docker Hub e imágenes propias

Alcance actualizado el 27/10/2026. Guía de comprobaciones, no prueba de ejecución.
Continuación del entorno y DB en [traspaso](../../docs/traspaso-011.md). No repetir
spikes ni instalar Core/Community. No ejecutar contra un nodo compartido sin
identidad/destino controlados. Seguir las dependencias de [tasks.md](tasks.md).

## 1. Preparación y bloqueo actual

- Reusar las dependencias bloqueadas, esquema aplicado y paquete Docker parcial.
  No resetear DB ni alterar migraciones aplicadas por retirar un proveedor.
- El gate definitivo quedó `incierto` antes de arrancar por `net0.type=veth`.
  Corrección en Git pendiente de distribuir; reconciliar el trabajo anterior,
  verificar ausencia/unidad y crear otra identidad para el nuevo ensayo.
- CT temporal 900011/discos/pool retirados; no tocar CT100 Draw.io. Perfiles
  definitivos pendientes hasta prueba real. Esto no cambió por editar documentos.
- Ubuntu 24.04/Docker, sistema no privilegiado, AppArmor/seccomp, recursos Medium,
  registry público/privado, CA, red/slots disjuntos y DNS/TLS preparados por técnico.
- No token root ni secretos en argv/repositorio/consola. No copiar identidades y
  certificados del laboratorio de Mauro al clúster universitario.

## 2. Gate real del único runtime

Instalar paquete definitivo después de construirlo y verificar:

1. Firewall externo antes de start; sin acceso desde guest al nodo, portal u otra
   cátedra; sólo dependencias/clientes autorizados. Probar desde fuera del guest.
2. Docker anidado, features cerradas, AppArmor/seccomp y límites reales <=Medium.
3. Pull por digest público y privado; retirar credencial de registry antes de start.
   ENTRYPOINT/CMD original, volúmenes propios, sin Docker socket o flags libres.
4. Borde HTTPS, pertenencia/configuración, acceso y prueba de aplicación antes
   de entregar/avisar. Estado incierto no es ni éxito ni ausencia del recurso.
5. systemd/captura segura sobreviven a SSH/UI/worker; reboot exige reconciliación.
   Revisar spool/journal/DB para secretos de ensayo, sin conservar logs crudos.

No habilitar perfiles por fakes o `exit 0`. No agregar otro perfil para una imagen
que sólo requiere datos del mismo contrato; rechazar condiciones no admitidas.

## 3. Pruebas proporcionales

Ejecutar sólo las selecciones afectadas del bloque. No repetir la regresión por
fase. Consultar nombres existentes antes de ejecutar: hay tests de tareas aún no
construidos. Ejemplos de áreas:

```bash
backend/venv/bin/python -m pytest -c infra/pytest.ini -q \
  infra/applications/tests/test_docker_runtime.py \
  infra/applications/tests/test_network_policy.py \
  infra/applications/tests/test_isolation_receipt.py
backend/venv/bin/python -m pytest -c backend/pytest.ini -q \
  backend/tests/test_biblioteca_despliegue_011.py
npm --prefix frontend test -- --run tests/biblioteca-despliegue.test.jsx
```

T051/T054 crearán los dos últimos archivos si faltan. Para carreras usar
`docker-compose.test.yml`, `TEST_DATABASE_URL` aislada y `--require-postgres` según
`backend/README.md`; nunca la DB del portal. Vitest/Playwright con API simulada se
identifican como tales. Integraciones infra necesitan `NAP_INFRA_INTEGRATION=1`
y revisión de su destino. Build/regresión completa sólo en el hito de cierre o
cuando el cambio lo justifique.

## 4. Dos imágenes de aceptación

- **Docker Hub**: buscar `traefik/whoami`, seleccionar una versión y fijar digest
  de plataforma por el resolver; comprobar página y ausencia de cookies NAP filtradas.
- **Imagen propia**: `infra/applications/fixtures/campus-demo/`, con salud y dato
  persistente. El desarrollador construye/publica en registry de ensayo, no el portal.
  Reusar esta imagen para comprobar pull privado y persistencia.

```bash
docker build -t "${NAP011_TEST_REGISTRY:?Configurar registry de ensayo}/nap/campus-demo:acceptance" \
  infra/applications/fixtures/campus-demo
docker push "${NAP011_TEST_REGISTRY:?}/nap/campus-demo:acceptance"
```

Esa variable sólo contiene host del registry. Autenticación/CA por archivos privados.
No publicar datos o credenciales institucionales en un registry público para probar.
No se exigen MariaDB/Caddy ni cuatro aplicaciones. El Caddy usado internamente como
borde HTTPS del runtime sí se conserva: no es el instalador Community retirado.

## 5. Recorrido del catálogo al acceso

1. Admin abre Agregar servicio → Docker Hub, busca y selecciona whoami. Usa el
   formulario OCI común; nombre/referencia/puerto, extras sólo necesarios.
   Alternativa Imagen propia: referencia de campus-demo. Alta <=3 min por entrada.
2. Cero CT/reserva al agregar. Sin Guardadas, preparar/publicar o formularios técnicos.
   Categorías inexistentes no bloquean; fallo Hub ofrece reintento/entrada manual.
3. Cátedra pide aplicación/propósito/fechas <=2 min, también Otro con imagen opcional.
   Admin aprueba y reserva. Futuro: programado, sin CT antes de fecha inicial.
4. Ver consola: negra/blanca, lectura, fases reales; cerrar/reabrir no reinstala.
5. Entrega sólo tras acceso comprobado, transición central y aviso. Abrir desde
   Servicios. Campus-demo escribe/lee dato y lo conserva tras stop/start/restart.
6. Dos cátedras reciben instancias/accesos/datos independientes de la misma oferta.
   No es necesario repetir toda la batería por elegir otra entrada de la misma imagen.
7. Retirar oferta bloquea nuevos pedidos; baja avisa destrucción y libera sólo
   después de confirmar ausencia propia. Ubuntu/Debian/Draw.io siguen intactos.

Ensayos secuenciales cuando falte capacidad. Dos operaciones simultáneas únicamente
para el ensayo de consola: p95 captura→pantalla <=5 s/apertura <=3 s, con límites
10 000 000 bytes/30 días, recorte visible y resultado/historia conservados.

## 6. Fallos, seguridad y cierre

- Respuesta start perdida, worker/SSH interrumpido, boot cambiado y doble clic:
  mismo intento cuando corresponde; reconciliar antes de nueva creación.
- Fallo CT antes del job: hitos seguros del portal consultables sin runner_job_id.
  Ingesta/ACK sólo después de commit, orden causal y sin fragmentos duplicados.
- Reintento tras ausencia confirmada mantiene secretos de aplicación del pedido,
  pero renueva identidad/nonce/TLS; nuevo pedido no hereda secretos anteriores.
- Tag cambiado, digest inaccesible, plataforma/tamaño incompatible, rate limit Hub:
  error claro, no cambio silencioso de versión ni oferta/entrega ficticia.
- Secretos partidos por chunks, ANSI/HTML, salida excesiva/desconocida: texto seguro,
  depuración previa, recorte/retención. Revocación impide nuevas lecturas/exportaciones.
- Agenda futura, datos persistentes, borrado incierto y recurso ajeno: no CT
  anticipado, pérdida de datos ni capacidad libre sin ausencia confirmada.

Registrar aceptación en `docs/evidencia/011/aceptacion.md`: dos imágenes, ambas
entradas, dos cátedras, recursos/perfil reales y alcance de cada comprobación.
Conservar evidencia previa fechada sin reescribirla como si el alcance siempre
hubiera sido éste. El entorno universitario sigue siendo una instalación distinta.
