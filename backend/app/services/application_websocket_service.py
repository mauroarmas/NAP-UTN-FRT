"""Bounded application WebSocket relay; no terminal or deployment commands."""
import asyncio
import re

from fastapi import HTTPException,Request,WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.services import aplicacion_access_service as access
from app.services.application_proxy_service import upstream_headers

MAX_MESSAGE=1024**2
RECHECK_SECONDS=5


class FixedConnect(connect):
    def process_redirect(self,exc):
        return exc  # Never retry another URI, even a same-host redirect.


def http_request(websocket):
    return Request({**websocket.scope,'type':'http','scheme':'https'})


async def relay(websocket,*,path,db,connector,ssl_context):
    tasks=[];accepted=False
    try:
        request=http_request(websocket)
        if path.startswith('_nap/'):
            raise HTTPException(403)
        actor,session,service,identity,instance=await access.autenticar_aplicacion(db,request)
        own=access.origen(service.id)
        if (not service.configuracion_despliegue_id or not instance['access'].get('websocket')
                or request.headers.get('origin')!=own):raise HTTPException(403)
        protocols=request.headers.get('sec-websocket-protocol','')
        if len(protocols)>1024:raise HTTPException(400)
        offered=[p.strip() for p in protocols.split(',') if p.strip()]
        if len(offered)>10 or any(not re.fullmatch(r'[A-Za-z0-9!#$%&\'*+.^_`|~-]{1,128}',p) for p in offered):raise HTTPException(400)
        headers=upstream_headers(request,instance)
        headers.pop('Host',None);headers.pop('Origin',None);headers.pop('Accept-Encoding',None)
        host=instance['host']+(':'+str(instance['port']) if instance['port']!=443 else '')
        uri='wss://'+host+'/'+path+('?' + request.url.query if request.url.query else '')
        await db.commit()
        async with connector(uri,host=instance['address'],port=instance['port'],server_hostname=instance['host'],
                ssl=ssl_context,origin='https://'+host,additional_headers=headers,subprotocols=offered or None,
                proxy=None,compression=None,open_timeout=5,close_timeout=2,max_size=MAX_MESSAGE,max_queue=16) as upstream:
            if upstream.subprotocol is not None and upstream.subprotocol not in offered:raise HTTPException(403)
            await websocket.accept(subprotocol=upstream.subprotocol);accepted=True
            async def to_application():
                while True:
                    message=await websocket.receive()
                    if message['type']=='websocket.disconnect':return
                    value=message.get('bytes') if message.get('bytes') is not None else message.get('text','')
                    if len(value.encode('utf-8') if isinstance(value,str) else value)>MAX_MESSAGE:
                        await websocket.close(code=1009);return
                    await upstream.send(value)
            async def to_browser():
                async for value in upstream:
                    if isinstance(value,bytes):await websocket.send_bytes(value)
                    else:await websocket.send_text(value)
            async def watch_access():
                while True:
                    await asyncio.sleep(RECHECK_SECONDS)
                    _,_,current,current_identity,target=await access.autenticar_aplicacion(db,request)
                    if current.id!=service.id or current_identity.id!=identity.id or target!=instance:raise HTTPException(403)
                    await db.commit()
            tasks=[asyncio.create_task(action()) for action in (to_application,to_browser,watch_access)]
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() is not None:raise task.exception()
    except HTTPException:
        await websocket.close(code=1008)
    except (WebSocketDisconnect,ConnectionClosed):
        pass
    except asyncio.CancelledError:raise
    except Exception:
        await websocket.close(code=1011)
    finally:
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        await db.rollback()  # No transaction survives the connection or revocation.
        if accepted:
            try:await websocket.close(code=1000)
            except RuntimeError:pass
