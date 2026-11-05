# Contrato: `console_access_profile` (configuración privada)

Archivo/valor privado de la instalación; nunca versionado con valores reales (ejemplo con marcadores en `infra/production/settings.example.json`).

```json
{
  "cluster_uuid": "<uuid del clúster>",
  "pve_version": "<versión comprobada>",
  "gate": { "evidencia_ref": "<uuid de la evidencia>", "sha256": "<hash de la evidencia>" },
  "nodos": { "<nodo>": { "host": "<dirección alcanzable por el navegador>", "port": 8006 } },
  "identities": {
    "<identidad@dominio>": {
      "usuario_id": 0,
      "revision_admin": 0,
      "referencia_institucional": "<acta o ticket>",
      "catedras": { "<id de cátedra>": 0 }
    }
  }
}
```

## Reglas

- `cluster_uuid` y `pve_version` deben coincidir con el perfil de infraestructura y con la evidencia.
- `gate.evidencia_ref` y `gate.sha256` seleccionan una evidencia `revocacion_consola` real y un trámite `completado`.
- `nodos` es obligatorio; sin él la consola permanece cerrada.
- Cada identidad se corresponde con una persona con `inventario_consola = asignada`; las revisiones deben coincidir con las vigentes en el portal o la persona queda sin consola.
- Cambiar clúster, versión, evidencia o una revisión invalida la habilitación (FR-011).

## Cambios de la feature 022

- `identities` **ya no se usa**: la identidad individual y su alcance los gestiona el portal (`identidades_consola`).
- `nodos[<nodo>]` admite `portal_host` opcional: la dirección con la que el **portal** alcanza el nodo (y con la que se verifica su certificado); `host` queda para el navegador (respaldo de administración).
