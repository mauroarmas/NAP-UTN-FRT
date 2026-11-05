# Respaldo externo de la instalación

Es una responsabilidad de operación de infraestructura; el portal no implementa un módulo de backup ni lo inicia al arrancar.

Estado acordado el 2026-10-21: el clúster y su red están en armado; actualmente se trabaja con la VM local. Destino externo, custodios y credenciales de ese destino pendientes de definición con el cliente. La VM permite ensayar copia/restauración en un entorno separado; ese ensayo no acredita la política externa diaria.

Política objetivo: copia diaria cifrada fuera del equipo/VM de origen, siete diarias y cuatro semanales, integridad comprobada y restauración periódica. La clave de descifrado debe tener custodia independiente del equipo origen. No guardar contraseñas, APP_KEY ni material de keyring en este directorio.

Inventario, corte consistente, responsabilidades, retención, recuperación y pendientes están en [docs/operacion-respaldos.md](../../docs/operacion-respaldos.md). Antes de automatizar, completar destino/operador/custodio y ensayar con un conjunto de prueba. No se instaló ningún cron, timer ni tarea remota.
