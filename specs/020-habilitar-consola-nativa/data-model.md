# Data Model: Habilitar la consola nativa

No hay tablas ni columnas nuevas. Se reutiliza el modelo de la spec 009 y se amplía **una clave de configuración privada**.

## Entidades existentes que se usan

| Entidad | Campos relevantes | Uso en esta feature |
|---|---|---|
| `usuarios` | `identidad_consola`, `inventario_consola` (`asignada`/`sin_identidad`/desconocida), `inventario_consola_actor`, `inventario_consola_ref`, `revision_admin` | Inventario institucional de quién tiene qué identidad individual (importador). |
| `cambios_acceso_consola` | `estado` (`pendiente`/`revocacion_fallida`/`completado`), `identidad_nativa`, `revision_esperada`, `scopes_propuestos`, `evidencia_id`, `solicitada_at`, `completada_at` | Trámite que sustenta la evidencia del ensayo. |
| `evidencias` (`tipo=revocacion_consola`) | documento canónico, `sha256`, `entorno`, `observado_at`, `resultado.{cluster_uuid, pve_version, identidad_nativa, scopes_resultantes, cambio_consola_id}` | Prueba real de revocación. |
| `identidades_infraestructura` | `cluster_id`, `servicio_id`, `estado`, `ownership_verificada_at`, `pool_catedra`, `vmid`, `nodo` | Condición para ofrecer la consola de un servicio. |
| `servicios` | `proxmox_node`, `proxmox_vmid`, `estado`, `identidad_infraestructura_id` | Nodo que aloja el contenedor y destino de consola. |

## Configuración privada ampliada: `console_access_profile`

Ver [contracts/console-profile.md](contracts/console-profile.md). Clave nueva:

- `nodos`: mapa `nombre de nodo → { host, port }` con la dirección que usa **el navegador de la persona**. Obligatorio para resolver el destino (FR-016); un nodo ausente no se usa como destino ni como alternativa.

## Reglas de validación

- Todo nodo con contenedores de servicios debe figurar en `nodos`; si falta, la consola de esos servicios responde "no habilitada" (cierra en falla).
- `identities[*]` sigue exigiendo `usuario_id`, `revision_admin`, `referencia_institucional` y `catedras` con revisión por cátedra.
- Una identidad pertenece a una sola persona (verificado por el inventario).

## Transiciones

Sin estados nuevos. El trámite sigue: `pendiente` → (`revocacion_fallida` ↔ reintento) → `completado`.
