"""Terminal web de la consola (feature 022): WebSocket del portal. Ver `terminal_relay_service` y contracts/terminal-ws.md."""
from fastapi import APIRouter, WebSocket

from app.database import AsyncSessionLocal
from app.services import terminal_relay_service
from app.services.auth_service import origin_valido

router = APIRouter(tags=['Terminal'])


@router.websocket('/servicios/{servicio_id}/terminal')
async def terminal(websocket: WebSocket, servicio_id: int):
    # El `Origin` se comprueba ANTES de aceptar: equivale al control de origen de las peticiones que modifican datos.
    try:
        origin_valido(websocket)
    except Exception:
        await websocket.close(code=1008)
        return
    await terminal_relay_service.servir(websocket, AsyncSessionLocal, servicio_id)
