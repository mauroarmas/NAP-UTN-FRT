# Quickstart Validation Guide: Notificaciones por Email y Gestión de Contraseñas Provisorias

**Feature Branch**: `008-notificaciones-email-usuarios-pedidos`  
**Date**: 2026-10-11  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## 1. Prerrequisitos

1. **Entorno Backend Activo**:
   - Base de datos PostgreSQL con migraciones de Alembic aplicadas (`alembic upgrade head`).
   - Servidor FastAPI corriendo en `http://localhost:8000`.
   - Variables de entorno SMTP configuradas en `.env` (o servidor mock SMTP en desarrollo).
2. **Entorno Frontend Activo**:
   - Servidor Vite en `http://localhost:5173`.
3. **Usuario Administrador**:
   - Cuenta `admin` activa (generada por `python scripts/seed_admin.py`).

---

## 2. Escenarios de Validación End-to-End

### Escenario A: Alta de Docente con Clave Provisoria por Correo
1. **Acción**: Iniciar sesión como `admin` en el portal web y dirigirse a `/usuarios`.
2. **Verificación visual**: Comprobar que el botón principal dice **"Nuevo usuario"** con ícono `UserPlus` (y no "Invitar usuario").
3. **Formulario**:
   - Presionar "Nuevo usuario".
   - Confirmar que el formulario **no** contiene campo para tipear contraseña.
   - Completar: Nombre: "Prof. Alberto Gómez", Username: "agomez", Email: "agomez@frt.utn.edu.ar", Rol: "Responsable de cátedra", y seleccionar una cátedra disponible.
   - Confirmar la creación.
4. **Resultado esperado**:
   - La API responde `201 Created` en menos de 500 ms.
   - El usuario se visualiza en la tabla de cuentas.
   - El servicio despacha en segundo plano un correo a `agomez@frt.utn.edu.ar` con su usuario, clave provisoria generada y enlace al portal.

---

### Escenario B: Primer Ingreso y Bloqueo Obligatorio de Contraseña
1. **Acción**: Cerrar sesión e ingresar en `/login` utilizando las credenciales provisorias (`agomez` y la contraseña enviada en el correo).
2. **Resultado esperado**:
   - La autenticación es exitosa.
   - Se despliega de forma inmediata un modal bloqueante que impide navegar: *"Primer ingreso: Es obligatorio cambiar su contraseña provisoria antes de continuar"*.
3. **Validación de error**:
   - Intentar ingresar contraseñas que no coinciden o de menos de 8 caracteres: el sistema muestra mensaje de error y no permite avanzar.
4. **Confirmación exitosa**:
   - Ingresar una nueva contraseña válida (ej: `Docente2026!`) y su confirmación.
   - Presionar "Guardar y Continuar".
5. **Resultado esperado**:
   - El modal se cierra, la cuenta queda con `debe_cambiar_password = false`, y el docente accede al dashboard con sus cátedras asignadas.

---

### Escenario C: Notificaciones de Correo en el Flujo de Pedidos
1. **Creación de Pedido**:
   - Con la sesión de `agomez`, ir a `/pedidos` y crear un nuevo pedido para su cátedra.
   - **Resultado**: Los administradores con `recibir_notificaciones_email = true` reciben un correo: *"Nuevo Pedido Solicitado: Cátedra X por Prof. Alberto Gómez"*.
2. **Solicitud de Ajustes**:
   - El administrador ingresa al pedido y presiona "Solicitar Ajustes" ingresando: *"Favor de reducir memoria a 4GB"*.
   - **Resultado**: El docente recibe un correo con las observaciones indicadas y enlace directo al pedido.
3. **Reenvío**:
   - El docente corrige su pedido y lo reenvía.
   - **Resultado**: El administrador recibe correo avisando que el pedido fue corregido y reenviado.
4. **Aprobación y Despliegue**:
   - El administrador aprueba el pedido y se concreta el despliegue a estado `activo`.
   - **Resultado**: El docente recibe un correo confirmando la aprobación y disponibilidad de su contenedor/servicio.

---

## 3. Comandos de Verificación Automatizada

Ejecutar la suite de pruebas unitarias y de integración para validar el flujo completo:

```bash
# Backend pytest suite
backend/venv/bin/pytest backend/tests/test_email_service.py backend/tests/test_alta_usuario_password.py backend/tests/test_pedidos_notificaciones.py -v
```

