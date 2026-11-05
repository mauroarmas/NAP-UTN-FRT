# Quickstart: validar el usuario no root en la consola

Prerrequisitos: laboratorio encendido (frt y pve91, quórum, NFS), maestros SSH abiertos, la consola de la 020 habilitada para una persona de prueba, paquete de nodo actualizado **antes** que el portal.

1. **Nodos primero**: reinstalar el paquete de nodo en frt y pve91 (`git archive` + `install.py` + `install.sh`); comprobar que el `policy_digest` no cambió (los perfiles Docker siguen vigentes).
2. **Servicio nuevo**: pedir y desplegar un Linux IaaS; «Revelar acceso inicial» debe mostrar `nap`; abrir la consola e iniciar sesión como `nap`; `sudo` funciona; `root` es rechazado; SSH por contraseña es rechazado y por clave sigue entrando.
3. **Servicio entregado**: con el #42 (o uno equivalente), crear un archivo, actualizar el acceso desde administración, comprobar que el archivo y la clave SSH siguen igual, que `nap` entra por consola con la contraseña nueva y que la de `root` ya no sirve.
4. **Idempotencia**: repetir la actualización 3 veces; la contraseña de `nap` ya revelada no cambia.
5. **Fallo controlado**: actualizar con el servicio detenido (409) y cortar el nodo durante la operación (resultado incierto, reintento con la misma contraseña).
6. **Secretos**: buscar la contraseña en registros del portal y del nodo, errores y auditoría tras los pasos anteriores: no aparece.
7. **Limpieza**: dar de baja los servicios de prueba.

Pruebas automáticas: `pytest infra/runner/tests backend/tests/test_acceso_consola_021.py backend/tests/test_policy_digest*.py`.
