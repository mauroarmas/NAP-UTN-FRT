# Conectar NAP al clúster universitario

Contrato de preparación inicial, 25 de octubre de 2026. Permite preparar el software y archivos de configuración ahora y completar los valores reales con infraestructura. No acredita que existan red, certificados, imágenes o permisos institucionales.

## Información que entrega infraestructura

| Elemento | Información o artefacto que debe comprobarse |
|---|---|
| PVE | UUID institucional de clúster, versión, nodos, cuenta/token dedicado, privilegios efectivos y CA pública verificada. |
| Capacidad | Storages con contenido rootdir, identidad compartida/local y márgenes; no confundir disco del host con volumen de servicio. |
| Red | Bridge/VLAN, DHCP, rutas y rangos autorizados de invitados/clientes; conectividad desde el equipo docente/alumno. |
| Pool de aplicaciones | UUID nuevos preasignados, FQDN/IP, MAC reservada en DHCP, certificados/clave/CA por identidad y productos permitidos. |
| Runner | Cuenta dedicada con forced-command, hostkeys verificadas, claves privadas fuera del repositorio, imágenes/bundles y registro root con hashes idénticos al catálogo. |
| Consola | Identidades individuales/pools, inventario de ACL heredadas y prueba de terminación de sesiones previas. |
| Operación | SMTP, nombre/certificado HTTPS del portal, destino externo de respaldos, responsables y procedimiento de restauración. |

No se trasladan las credenciales temporales de la VM como valores predeterminados del clúster. La preparación técnica de imágenes/recetas y su validación se hace por versión; los despliegues ordinarios posteriores usan el catálogo.

## Pool preautorizado de DNS/TLS/DHCP

Infraestructura genera los UUID una vez al preparar el pool y configura en lote DNS, certificados y DHCP. En el `network_profiles` privado del portal, cada entrada de `instances` tiene esta forma ilustrativa:

```json
{
  "11111111-1111-4111-8111-111111111111": {
    "host": "pg01.example.edu",
    "address": "10.20.0.10",
    "mac_address": "02:00:00:00:00:10",
    "products": ["postgresql"]
  },
  "22222222-2222-4222-8222-222222222222": {
    "host": "libros01.example.edu",
    "address": "10.20.0.11",
    "mac_address": "02:00:00:00:00:11",
    "products": ["bookstack"]
  }
}
```

Son ejemplos; reemplazarlos por identidades y direcciones efectivamente preparadas. El perfil padre incluye `bridge`, `nodes`, `allowed_cidrs`, `client_cidrs` y, si corresponde, `vlan_tag`. FQDN, dirección y MAC no se duplican en los pools configurados. La MAC debe ser local/unicast con prefijo `02`. Preparar al menos dos entradas por producto para su aceptación y suficientes para los despliegues previstos. Un destino preparado no es una cuota de cátedra.

El registro root del runner conserva los mismos UUID/FQDN/IP dentro de `networks[network_profile_id].instances`, y para cada UUID añade `tls_certificate_path`, `tls_private_key_path` y `tls_ca_path` con archivos reales controlados por root. La clave privada conserva permisos restrictivos. No montar esas claves de aplicaciones en el portal ni enviarlas en formularios. Los CIDR del runner usan su campo `subnets` y deben coincidir con los rangos permitidos del portal.

Al reclamar una instancia PostgreSQL/BookStack, NAP toma el lock común, selecciona un UUID del pool que no tenga identidad histórica y persiste UUID, nonce, perfil y snapshot de host/IP/MAC/bridge/CIDR antes del POST a PVE. La MAC se incluye en `net0` para obtener la reserva DHCP prevista. El runner reconoce ese UUID sin actualizar perfiles durante el despliegue. Cada instancia genera sus propias contraseñas; BookStack también genera APP_KEY propia.

Los reintentos conservan UUID, destino y claves. Cambiar el destino preparado después de reclamarlo bloquea la preparación y exige revisión; no se reasigna silenciosamente. Si el pool no tiene una entrada válida/disponible, se rechaza antes de crear, con diagnóstico. Los UUID consumidos no se reutilizan, incluso tras retirar el recurso: ampliar el pool con nuevas identidades y no borrar historia para reciclar certificados. Restaurar el portal exige reconciliar las identidades externas antes de reanudar; no arrancar una copia anterior contra el mismo pool sin ese control.

Linux no requiere este pool de certificados: conserva identidad aleatoria, DHCP en su red autorizada y acceso por consola individual condicionada al gate.

## Gate de consola por instalación

`console_access_profile` es una declaración institucional privada, no un booleano de habilitación. Ejemplo de estructura, con referencias que deben existir en la DB de esa instalación:

```json
{
  "cluster_uuid": "UUID_REAL_DEL_CLUSTER",
  "pve_version": "VERSION_COMPROBADA",
  "gate": {"evidencia_ref": "UUID_EVIDENCIA_REGISTRADA", "sha256": "SHA256_CANONICO"},
  "identities": {
    "docente@pve": {
      "usuario_id": 12,
      "revision_admin": 3,
      "referencia_institucional": "ACTA_CONCESION_POOLS",
      "catedras": {"7": 2}
    }
  }
}
```

La evidencia es `revocacion_consola`, real, íntegra y de un trámite completado; su resultado incluye `cluster_uuid` y `pve_version` además de identidad, revisión, scopes y pruebas de sesiones/URL/otros accesos legítimos. Registrarla durante el trámite y confirmarlo por los controles normales. Configurar luego su UUID/hash como prueba del procedimiento de esa instalación.

Cada concesión identifica un usuario NAP inventariado, su revisión administrativa y las revisiones de cátedras cuyos pools se comprobaron en PVE. Los cambios de titularidad/rol invalidan declaraciones viejas y los trámites pendientes bloquean el alcance. La consola verifica además la identidad propia del servicio, clúster, VMID/nodo, pool y vigencia. No se acepta una prueba de otro clúster ni una identidad compartida. No copiar el archivo de staging para abrir la consola.

## Comprobaciones de conexión y aceptación

1. Completar archivos privados de configuración, permisos y artefactos según [DOCKER.md](../DOCKER.md).
2. Ejecutar `python -m scripts.preflight --datos --inventario` desde el entorno configurado; revisar hallazgos sin imprimir secretos.
3. Construir/ensayar/importar/publicar según [infra/services/README.md](../infra/services/README.md), sin convertir pruebas sintéticas en evidencia real. Las versiones validadas en la VM requieren validación/evidencia para el clúster que las recibirá.
4. Probar solicitudes y despliegues con ambos roles, falta de saldo, fechas futuras, operación fallida/reintento y revocación nativa. Repetir desde otra computadora en la red prevista.
5. Probar PostgreSQL con escritura/lectura y persistencia, y BookStack con libro/página, dos lectores individuales, archivos privados y revocación aislada.
6. Completar SMTP, restore separado de portal+keyring y aplicaciones, comparación de datos y tiempos observados. Registrar responsables/destino externo cuando se acuerden.

Aceptación pendiente: T102, T119, T131 y T133. Las regresiones locales no las marcan completadas. La revisión de manuales por una persona ajena al desarrollo se coordina junto al recorrido de T119.
