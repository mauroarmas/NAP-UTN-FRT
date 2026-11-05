# Quickstart de validación: acceso SSH a Linux IaaS

Guía para comprobar la feature de punta a punta en el laboratorio frt + pve91. Los detalles de campos están en
[data-model.md](data-model.md) y [contracts/](contracts/).

## Prerrequisitos

- Laboratorio encendido (TrueNAS → nap1 → nap2), portal arriba, maestros SSH a `.90` y `.91` abiertos por Ivan.
- Paquete de nodo reinstalado en ambos nodos con `docs/infraestructura-laboratorio/scripts/actualizar-nodos-011.sh --aplicar`
  (el plan debe mostrar `iaas_access.py` como archivo nuevo y **ningún** cambio en los archivos del `policy_digest`).
- Plantilla `ubuntu-24.04-standard` disponible en el nodo elegido.
- Un par de claves de prueba: `ssh-keygen -t ed25519 -f ~/.ssh/nap-prueba -N ''` en la notebook (la parte pública es lo que se pega).

## Verificaciones previas (antes de tocar el portal)

1. `pct exec <vmid-de-prueba> -- systemctl is-enabled ssh` en un LXC Ubuntu: confirma R10 (la plantilla trae `openssh-server`).
2. Prueba unitaria `policy_digest()` antes/después del cambio: debe ser idéntico (restricción R4).

## Escenarios

| # | Pasos | Resultado esperado |
|---|---|---|
| 1 | Pedir un Ubuntu en `pve91` pegando la clave pública. Aprobar. | Queda `RUNNING / utilizable` sin acciones manuales en el nodo. El detalle muestra `ssh nap@<ip>` y la huella. |
| 2 | Desde la notebook: `ssh -i ~/.ssh/nap-prueba nap@<ip>`; luego `sudo -n true`. | Entra; la elevación funciona sin contraseña. |
| 3 | `ssh root@<ip>`; `ssh -o PreferredAuthentications=password nap@<ip>`; entrar con otra clave. | Los tres son rechazados. |
| 4 | Pegar una clave privada / una línea mal formada / varias claves en el pedido. | Mensaje comprensible; el pedido no avanza. |
| 5 | Detener e iniciar el servicio desde el portal. | La misma clave entra. |
| 6 | Reemplazar la clave desde el portal con un par nuevo. | La nueva entra; la anterior es rechazada; el historial muestra el reemplazo con la huella. |
| 7 | Otra persona (sin ser titular ni admin) intenta `PUT /servicios/N/acceso-ssh`. | 403. |
| 8 | Servicio ya entregado sin clave (el #41 en pve91): registrar una clave. | Obtiene acceso SSH sin darlo de baja. La consola sigue sin cambiar. |
| 9 | Reiniciar `pve91` con `systemctl reboot`; iniciar el servicio por el portal. | No se declara utilizable hasta que `probe` confirma; entra con la misma clave. |
| 10 | Dar de baja y pedir otro con el mismo `vmid` si el nodo lo reutiliza. | La clave anterior no entra al nuevo. |
| 11 | Revisar historial, registros del worker y la respuesta de errores. | Solo huellas; ninguna clave completa ni contraseña. |
| 12 | Regresión: pedir/usar MariaDB y nginx; correr las pruebas de consola IaaS. | Sin cambios de comportamiento. |

## Pruebas automáticas

- Backend (`backend/tests`): `ssh_keys` (formatos válidos e inválidos, huella), schema de pedido, servicio de acceso (`acceso_ssh` en cada estado),
  endpoint `PUT` (permisos, idempotencia, `operacion_en_curso`), operación `acceso_ssh` (idempotente por revisión, incierta → misma revisión).
- Runner (`infra/runner/tests`): validación estricta del protocolo, identidad, `configure` y `probe` con `run_command` simulado,
  y una prueba de que la clave **no** aparece en ningún `argv`.
- Frontend: formulario de pedido (campo, error), bloque de acceso (copiar comando, estados), modal de cambio de clave.
- Prueba de no regresión: `policy_digest()` constante.

Las pruebas automáticas no acreditan el despliegue real: lo acredita la tabla de escenarios ejecutada en frt y pve91.
