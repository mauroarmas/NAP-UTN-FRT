"""Concurrencia real de códigos de un uso y entrega idempotente, sin Proxmox."""
import asyncio
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import select,func
from app.services import aplicacion_access_service as access
from app.models.pedido import Pedido,EstadoPedido
from app.models.evento_seguridad import EventoSeguridad
from tests.test_acceso_aplicacion import drawio,app_client,test_open_one_use_private_proxy_delivery_and_no_password
from tests.test_entrega_acceso_009 import prepared_access
from tests.test_evidencias_009 import evidence_definition,prepared_instance_document

async def test_un_codigo_solo_puede_consumirse_una_vez(client,db,pg_sessions,drawio,auth_catedra):
    result=await client.post(f'/servicios/{drawio.id}/abrir-aplicacion',headers=auth_catedra,json={})
    assert result.status_code==200,result.text
    def request(cookie=None):
        headers=[(b'host',f'app-{drawio.id}.apps.example.edu'.encode()),(b'origin',b'http://test')]
        if cookie:headers.append((b'cookie',(access.COOKIE+'='+cookie).encode()))
        return Request({'type':'http','method':'POST','scheme':'https','server':(f'app-{drawio.id}.apps.example.edu',443),
            'path':'/_nap/entrar','query_string':b'','headers':headers})
    async def consume():
        async with pg_sessions() as session:
            try:
                cookie,_=await access.consumir_codigo(session,request(),result.json()['codigo'])
                await session.commit();return cookie
            except HTTPException as exc:
                await session.rollback();return exc.status_code
    results=await asyncio.gather(consume(),consume())
    assert [value for value in results if isinstance(value,int)]==[401]
    cookie=next(value for value in results if isinstance(value,str))
    async def confirm():
        async with pg_sessions() as session:await access.confirmar_apertura(session,request(cookie))
    await asyncio.gather(confirm(),confirm())
    assert (await db.get(Pedido,drawio.pedido_id,populate_existing=True)).estado==EstadoPedido.ACTIVO
    assert await db.scalar(select(func.count()).select_from(EventoSeguridad).where(EventoSeguridad.accion=='acceso_aplicacion_confirmado'))==1
