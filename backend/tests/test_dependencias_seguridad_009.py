import base64
from datetime import timedelta
import hashlib
import hmac
import json
from urllib.parse import urlencode

from app.config import get_settings
from app.utils.clock import clock
from app.utils.security import decode_access_token,create_access_token


def signed_legacy(payload,*,algorithm='HS256',digest=hashlib.sha256):
    def part(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=')
    body=part({'alg':algorithm,'typ':'JWT'})+b'.'+part(payload)
    signature=hmac.new(get_settings().secret_key.encode(),body,digest).digest()
    return (body+b'.'+base64.urlsafe_b64encode(signature).rstrip(b'=')).decode()


def test_hmac_jwt_keeps_legacy_format_and_rejects_other_algorithms_missing_or_invalid_expiry():
    payload={'sub':'1','exp':int(clock.now().timestamp())+300,'sid':'fixture'}
    assert decode_access_token(signed_legacy(payload))==payload
    assert decode_access_token(create_access_token({'sub':'1'},timedelta(minutes=5)))['sub']=='1'
    assert decode_access_token(signed_legacy(payload,algorithm='HS384',digest=hashlib.sha384)) is None
    assert decode_access_token(signed_legacy({'sub':'1'})) is None
    assert decode_access_token(signed_legacy(payload|{'exp':True})) is None
    assert decode_access_token(signed_legacy(payload|{'exp':int(clock.now().timestamp())-1})) is None
    assert decode_access_token(signed_legacy(payload)+'altered') is None


def test_temporal_claims_use_the_same_injected_clock(monkeypatch):
    instant=clock.now();monkeypatch.setattr(clock,'now',lambda:instant)
    token=signed_legacy({'sub':'1','exp':int(instant.timestamp())+300,'nbf':int(instant.timestamp())+60})
    assert decode_access_token(token) is None
    instant+=timedelta(seconds=61)
    assert decode_access_token(token)['sub']=='1'


async def test_urlencoded_field_limit_applies_before_authentication(client,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('No autenticar un formulario que excede el límite')
    monkeypatch.setattr('app.routers.auth.verificar_password_async',forbidden)
    content=urlencode([('username','fixture'),('password','fixture-safe-009'),*[(f'f{i}','v') for i in range(1100)]])
    response=await client.post('/auth/login',content=content,headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert response.status_code==400
