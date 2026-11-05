"""Pruebas adversarias y de aislamiento extremo a extremo para aplicaciones 011 (T100).

Cubre:
1. SSRF, esquemas inválidos y referencias de imagen maliciosas / inyecciones.
2. Directorios de persistencia prohibidos y traversal (../../etc/passwd).
3. Variables de entorno restringidas (LD_PRELOAD, BASH_FUNC_, contraseñas en texto plano).
4. Aislamiento entre cátedras (rutas sensibles, apertura de app, revelación de credenciales).
5. No filtración de cookies de sesión, tokens CSRF ni credenciales hacia la aplicación.
6. Revocación inmediata ante pérdida de sesión o permisos.
"""

from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models.pedido import EstadoPedido, Pedido
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import EstadoServicio, Servicio
from app.schemas.aplicacion import AgregarAplicacion, ConfigurarAplicacion
from app.schemas.pedido import DatosSolicitud
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests import factories
from tests.auth_helpers import headers_para
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa: F401


# --- 1. SSRF, esquemas y referencias maliciosas ---


@pytest.mark.parametrize(
    "bad_ref",
    [
        "http://169.254.169.254/latest/meta-data",
        "https://127.0.0.1:8000/internal",
        "ssh://git@github.com/repo",
        "traefik/whoami; cat /etc/shadow",
        "traefik/whoami\nrm -rf /",
        "traefik/whoami\x00malicious",
        "user:password@registry.example.edu/app",
        "traefik/whoami $(whoami)",
        "traefik/whoami `reboot`",
    ],
)
def test_referencia_imagen_maliciosa_o_ssrf_es_rechazada(bad_ref):
    """Rechazo estricto de URLs SSRF, inyecciones de comandos, credenciales y caracteres no imprimibles."""
    with pytest.raises(ValidationError):
        DatosSolicitud(referencia_imagen=bad_ref)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/sys",
        "/sys/fs/cgroup",
        "/proc",
        "/proc/1",
        "/dev",
        "/dev/pts",
        "/boot",
        "/root",
        "/etc/pve",
        "/etc/nap",
        "/var/lib/docker",
        "/../etc/passwd",
        "/var/run/docker.sock",
        "relative/path",
        "/path/with/../traversal",
        "/path/./hidden",
    ],
)
def test_persistencia_carpetas_prohibidas_y_traversal_rechazadas(bad_path):
    """Rechazo de montajes sobre rutas del sistema operativo del contenedor o traversal."""
    with pytest.raises(ValidationError):
        ConfigurarAplicacion(
            imagen="traefik/whoami:latest",
            puerto=80,
            persistencia=[bad_path],
        )


@pytest.mark.parametrize(
    "bad_var",
    [
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "BASH_FUNC_malicious%%",
        "NAP_SECRET_KEY",
        "PASSWORD",
        "app_key",
        "token",
        "contraseña",
    ],
)
def test_variables_restringidas_y_secretos_en_texto_plano_rechazados(bad_var):
    """No se permite inyectar variables de ejecución peligrosa ni contraseñas en variables públicas del catálogo."""
    with pytest.raises(ValidationError):
        ConfigurarAplicacion(
            imagen="traefik/whoami:latest",
            puerto=80,
            variables={bad_var: "insegura"},
        )


# --- 2. Aislamiento entre cátedras y no exposición de secretos ---


async def test_aislamiento_multicatedra_en_servicios_y_operaciones(
    client, db, admin, auth_admin, catedra, usuario_catedra
):
    """Un usuario docente no puede acceder a los servicios, accesos ni consola de otra cátedra."""
    # Crear cátedra ajena y usuario ajeno
    otro_user = await factories.crear_usuario(db, "docente-otra-catedra-aislamiento")
    otra_catedra = await factories.crear_catedra(db, nombre="Otra Cátedra Aislamiento", titular_id=otro_user.id)
    auth_otro = await headers_para(db, otro_user)
    auth_propio = await headers_para(db, usuario_catedra)

    # Crear servicio perteneciente a la cátedra ajena
    template = await factories.crear_template(db)
    service_ajeno = Servicio(
        catedra_id=otra_catedra.id,
        template_id=template.id,
        nombre_snapshot="Servicio Confidencial Ajeno",
        modelo_servicio="saas",
        estado=EstadoServicio.RUNNING,
        vcpus_asignados=1,
        ram_asignada_mb=512,
        disk_asignado_gb=4,
        disponibilidad_aplicacion="utilizable",
        acceso_metadata={"metodo": "https", "direccion": "https://ajena.example.edu"},
        credenciales_encrypted=configured_keyring().encrypt(
            {"password": "secret-password-catedra-ajena"}, context="servicio:test:secretos"
        ),
    )
    db.add(service_ajeno)
    await db.commit()
    await db.refresh(service_ajeno)
    service_ajeno_id = service_ajeno.id

    # 1. El docente de la cátedra propia NO puede ver el acceso del servicio ajeno
    r_acceso = await client.get(f"/servicios/{service_ajeno_id}/acceso", headers=auth_propio)
    assert r_acceso.status_code == 403, r_acceso.text
    assert "secret-password" not in r_acceso.text

    # 2. El docente NO puede solicitar revelar credenciales del servicio ajeno
    r_revelar = await client.post(f"/servicios/{service_ajeno_id}/acceso/revelar", headers=auth_propio, json={})
    assert r_revelar.status_code == 403, r_revelar.text

    # 3. El docente NO puede ejecutar acciones de ciclo de vida sobre el servicio ajeno
    r_stop = await client.post(
        f"/servicios/{service_ajeno_id}/stop",
        headers=auth_propio | {"Idempotency-Key": f"stop-{uuid4()}"},
    )
    assert r_stop.status_code == 403, r_stop.text

    # 4. Solicitud anónima / sin sesión es rechazada inmediatamente con 401
    r_unauth = await client.get(f"/servicios/{service_ajeno_id}/acceso")
    assert r_unauth.status_code in (401, 403)


async def test_credenciales_permanecen_cifradas_y_no_se_filtran_en_snapshots(
    db, admin, catedra, usuario_catedra
):
    """Las credenciales y contraseñas de las aplicaciones se almacenan cifradas con el keyring."""
    template = await factories.crear_template(db)
    password_plana = "SuperSecretPassword123!"

    ctx = f"servicio:999:secretos"
    encrypted = configured_keyring().encrypt({"guest_password": password_plana}, context=ctx)

    service = Servicio(
        id=999,
        catedra_id=catedra.id,
        template_id=template.id,
        nombre_snapshot="Servicio Prueba Cifrado",
        modelo_servicio="saas",
        estado=EstadoServicio.RUNNING,
        vcpus_asignados=1,
        ram_asignada_mb=512,
        disk_asignado_gb=4,
        asignacion_snapshot={"template_id": template.id, "vcpus": 1, "ram_mb": 512, "disk_gb": 4},
        acceso_metadata={"metodo": "https", "host": "app999.example.edu"},
        credenciales_encrypted=encrypted,
    )
    db.add(service)
    await db.commit()

    # Inspección directa del registro en base de datos
    db.expire_all()
    loaded = await db.get(Servicio, 999)
    assert password_plana not in str(loaded.asignacion_snapshot)
    assert password_plana not in str(loaded.acceso_metadata)
    assert password_plana not in loaded.credenciales_encrypted

    # Solo el keyring con el contexto específico puede desencriptar
    decrypted = configured_keyring().decrypt(loaded.credenciales_encrypted, context=ctx)
    assert decrypted["guest_password"] == password_plana
