"""Decisiones locales indivisibles; el llamador confirma efecto e historia juntos."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text

from app.models.decision_idempotente import DecisionIdempotente
from app.utils.errors import error


FORBIDDEN = {'password', 'contraseña', 'secrets', 'credenciales', 'token', 'nonce', 'app_key', 'totp_secret'}


def safe_json(value):
    """Solo referencias y decisiones seguras, nunca cuerpos de revelado/auth."""
    value = jsonable_encoder(value)

    def inspect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in FORBIDDEN:
                    raise ValueError('Una decisión idempotente no almacena secretos')
                inspect(child)
        elif isinstance(item, list):
            for child in item:
                inspect(child)
    inspect(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class ResultadoDecision:
    status_code: int
    resultado: dict
    replayed: bool = False


async def ejecutar(db, *, actor_id, clave, metodo, ruta, payload, decidir, actor_tipo='usuario',
                   target_tipo=None, target_id=None):
    if not isinstance(clave, str) or not 1 <= len(clave) <= 128 or not clave.strip():
        raise error(422, 'idempotency_key_invalida', 'Indicá una clave idempotente de hasta 128 caracteres')
    if actor_tipo not in {'usuario', 'sistema'}:
        raise ValueError('Actor de decisión inválido')
    actor = str(actor_id)
    method = metodo.upper()
    fingerprint = hashlib.sha256(safe_json(payload).encode()).hexdigest()
    if db.bind.dialect.name == 'postgresql':
        digest = hashlib.sha256(f'{actor_tipo}:{actor}:{clave}'.encode()).digest()
        lock = -1 - (int.from_bytes(digest[:8], 'big') & ((1 << 62) - 1))
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
    previous = await db.scalar(select(DecisionIdempotente).where(
        DecisionIdempotente.actor_tipo == actor_tipo,
        DecisionIdempotente.actor_id_normalizado == actor,
        DecisionIdempotente.idempotency_key == clave,
    ))
    if previous:
        if (previous.metodo, previous.ruta_canonica, previous.request_hash) != (method, ruta, fingerprint):
            raise error(409, 'idempotency_key_reutilizada', 'La clave ya corresponde a otra acción o contenido')
        return ResultadoDecision(previous.response_status, deepcopy(previous.resultado_referencia), True)
    result = await decidir(db)
    if not isinstance(result, ResultadoDecision) or result.status_code not in {200, 201, 202, 204}:
        raise ValueError('Resultado de decisión inválido')
    safe_result = json.loads(safe_json(result.resultado))
    db.add(DecisionIdempotente(actor_tipo=actor_tipo, actor_id_normalizado=actor, idempotency_key=clave,
        metodo=method, ruta_canonica=ruta, request_hash=fingerprint, target_tipo=target_tipo,
        target_id=str(target_id) if target_id is not None else None,
        response_status=result.status_code, resultado_referencia=safe_result))
    await db.flush()
    # Sin commit interno: una excepción/rollback también elimina clave y efecto.
    return ResultadoDecision(result.status_code, safe_result)
