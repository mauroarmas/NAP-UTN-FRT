# Aceptación real de preparación — pendiente (T052)

No ejecutada. La configuración local observada tiene **0 builder_hosts**, **0 perfiles_ensayo** y ningún directorio de registro dinámico configurado. El código de la receta está sin commit, por lo que no tiene la revisión comprometida exigida por el constructor. No se iniciaron contenedores operativos, ni se importaron imágenes/credenciales ficticias para habilitar el flujo.

Para completar: preparar host separado y checkout comprometido, base/locks/fuentes verificadas, registros/hostkeys/montajes, pool y dos identidades de red con certificados. Seguir [quickstart](../../../specs/010-integrar-biblioteca-aplicaciones/quickstart.md#4-ensayo-real-y-publicación--us1us2). Conservar versión/revisión y digests reales; comprobar los dos ensayos con proveedor bloqueado, ciclo `.drawio`, perímetro, aislamiento, reinicio y limpieza por los tres motivos. Registrar `deployment_without_provider` de ambos UUID antes de validar/publicar.

Las pruebas locales se encuentran en [us2-pruebas.md](us2-pruebas.md). No equivalen a esta aceptación.
