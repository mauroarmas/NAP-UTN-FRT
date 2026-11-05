from fastapi import APIRouter, Depends, Request, Response, HTTPException, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.models.autenticacion import SesionAutenticacion
from app.schemas import auth as schemas
from app.schemas.usuario import UsuarioCreate, UsuarioResponse
from app.services import auth_service as auth, segundo_factor_service as factor, auth_intentos_service as intentos
from app.services.usuario_service import con_catedras
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.security import validar_password, verificar_password_async, hash_password_async

router = APIRouter(prefix='/auth', tags=['Autenticación'])
DUMMY_HASH = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxHAZs3dZ9zg72bHGSc.HnJlK7O'


async def get_auth_user(request: Request, db: AsyncSession = Depends(get_db)):
    user, _ = await auth.autenticar(db, request)
    return user


async def get_current_user(request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'operativo')
    from app.services.acceso_service import usuario_actual
    return await usuario_actual(db, user)


async def require_admin(current_user: Usuario = Depends(get_current_user)):
    if current_user.rol != RolUsuario.ADMIN:
        raise error(403, 'sin_permisos', 'Se requieren permisos de administrador')
    return current_user


def no_store(data, *, status=200):
    return JSONResponse(jsonable_encoder(data), status_code=status, headers={'Cache-Control': 'no-store'})


async def transition(db, user, session, *, codes=None, include_user=False):
    result = await auth.presentar(db, user, session, rotated=True)
    if include_user:
        result['usuario'] = await con_catedras(db, user)
    if codes is not None:
        result['codigos_recuperacion'] = codes
    response = no_store(result)
    await db.commit()
    auth.establecer_cookie(response, session, user)
    return response


async def sensitive(db, request, user, action):
    """El fallo conserva el contador; ninguna prueba secreta se registra."""
    account, origin = intentos.cuenta_identificador(user), intentos.origen_remoto(request)
    try:
        await intentos.comprobar_limite(db, account, origin)
        user = await auth.usuario_bloqueado(db, user)
        session = await db.get(SesionAutenticacion, request.state.auth_session.id, populate_existing=True)
        if session.revoked_at or session.auth_version != user.auth_version or db_utc(session.expira_at) <= clock.now():
            raise error(401, 'sesion_invalida', 'Ingresá nuevamente')
        return await action(user, session)
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get('codigo') == 'prueba_invalida':
            await intentos.registrar_fallo(db, account, origin)
            auth.auditar(db, user, 'autenticacion_prueba', resultado='denegado')
            await db.commit()
            await intentos.comprobar_limite(db, account, origin)
        elif exc.status_code == 429:
            auth.auditar(db, user, 'autenticacion_bloqueada', resultado='denegado')
            await db.commit()
        else:
            await db.rollback()
        raise


@router.post('/login')
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    auth.origin_valido(request)
    from app.services.restauracion_service import exigir_habilitacion
    await exigir_habilitacion(db, componente='api')
    if request.headers.get('x-nap-request') != '1':
        raise error(403, 'origen_no_permitido', 'Solicitud de ingreso no permitida')
    validar_password(form_data.password)
    supplied = form_data.username.strip().casefold()
    matches = (await db.scalars(select(Usuario).where((func.lower(Usuario.username) == supplied) | (func.lower(Usuario.email) == supplied)).limit(2))).all()
    user = matches[0] if len(matches) == 1 else None
    account, origin = intentos.cuenta_identificador(user, supplied), intentos.origen_remoto(request)
    await intentos.comprobar_limite(db, account, origin)
    encoded = user.password_hash if user else DUMMY_HASH
    valid = await verificar_password_async(form_data.password, encoded)
    if not valid or not user or not user.activo:
        await intentos.registrar_fallo(db, account, origin)
        auth.auditar(db, user, 'login', resultado='denegado')
        await db.commit()
        await intentos.comprobar_limite(db, account, origin)
        raise error(401, 'credenciales_invalidas', 'Usuario o contraseña incorrectos')
    user = await auth.usuario_bloqueado(db, user)
    if user.password_hash != encoded and not await verificar_password_async(form_data.password, user.password_hash):
        await db.rollback()
        raise error(401, 'credenciales_invalidas', 'Usuario o contraseña incorrectos')
    previous = None
    if request.cookies.get(auth.cookie_name()):
        try:
            _, previous = await auth.autenticar(db, request, mutation_csrf=False)
        except HTTPException:
            pass
    purpose = 'mfa_pending' if user.totp_habilitado else ('onboarding' if user.debe_cambiar_password else 'operativo')
    session = await auth.crear_sesion(db, user, purpose, anterior=previous)
    auth.auditar(db, user, 'login')
    return await transition(db, user, session)


@router.get('/me')
async def get_me(request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    session = request.state.auth_session
    result = await auth.presentar(db, user, session)
    if session.proposito == 'operativo':
        from app.services.acceso_service import usuario_actual
        await usuario_actual(db, user)
        result['usuario'] = await con_catedras(db, user)
    else:
        result['usuario'] = {key: getattr(user, key) for key in ['id', 'username', 'nombre', 'debe_cambiar_password', 'totp_habilitado']}
    return no_store(result)


@router.get('/csrf')
async def csrf(request: Request, user: Usuario = Depends(get_auth_user)):
    session = request.state.auth_session
    return no_store({'csrf_token': auth.csrf_token(session), 'expira_at': db_utc(session.expira_at)})


@router.post('/logout', status_code=204)
async def logout(request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    await auth.revocar(db, request.state.auth_session)
    auth.auditar(db, user, 'logout')
    await db.commit()
    response = Response(status_code=204)
    auth.borrar_cookie(response)
    return response


@router.post('/cambiar-password-inicial')
async def cambiar_password_inicial(data: schemas.CambiarPasswordInicialRequest, request: Request,
    user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'onboarding')
    async def action(current, previous):
        current.password_hash = await hash_password_async(data.nueva_password)
        current.debe_cambiar_password = False
        from app.services.notificacion_service import cancelar_bienvenidas
        await cancelar_bienvenidas(db, current)
        await auth.invalidar_todas(db, current)
        session = await auth.crear_sesion(db, current, 'operativo', mfa_at=previous.mfa_verified_at)
        auth.auditar(db, current, 'password_inicial_cambiada')
        return await transition(db, current, session, include_user=True)
    return await sensitive(db, request, user, action)


@router.post('/2fa/challenge/verify')
async def challenge_verify(data: schemas.Verify2FARequest, request: Request,
    user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'mfa_pending')
    async def action(current, previous):
        codes = await factor.verificar_login(db, current, previous, data.desafio_id, data.codigo_totp)
        session = await auth.crear_sesion(db, current, 'onboarding' if current.debe_cambiar_password else 'operativo', anterior=previous, mfa_at=clock.now())
        return await transition(db, current, session, codes=codes)
    return await sensitive(db, request, user, action)


async def setup_action(data, request, user, db, *, replacement=False):
    auth.exigir_proposito(request.state.auth_session, *(['operativo'] if replacement else ['operativo', 'recovery']))
    if request.state.auth_session.proposito == 'operativo' and data.password is None:
        raise error(422, 'datos_invalidos', 'Confirmá tu contraseña para configurar el factor')
    async def action(current, session):
        result = await factor.setup(db, current, session, password=data.password, replacement=replacement, codigo_totp=getattr(data, 'codigo_totp', None))
        await db.commit()
        return no_store(result)
    return await sensitive(db, request, user, action)


@router.post('/2fa/setup')
async def setup(data: schemas.Setup2FARequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await setup_action(data, request, user, db)


@router.post('/2fa/replacement/setup')
async def replacement_setup(data: schemas.PruebaTOTP, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await setup_action(data, request, user, db, replacement=True)


async def verify_setup_action(data, request, user, db, *, replacement=False):
    auth.exigir_proposito(request.state.auth_session, *(['operativo'] if replacement else ['operativo', 'recovery']))
    async def action(current, previous):
        codes = await factor.confirmar_setup(db, current, previous, data.desafio_id, data.codigo_totp, replacement=replacement)
        session = await auth.crear_sesion(db, current, 'onboarding' if current.debe_cambiar_password else 'operativo', mfa_at=clock.now())
        return await transition(db, current, session, codes=codes)
    return await sensitive(db, request, user, action)


@router.post('/2fa/verify')
async def verify_setup(data: schemas.Verify2FARequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await verify_setup_action(data, request, user, db)


@router.post('/2fa/replacement/verify')
async def replacement_verify(data: schemas.Verify2FARequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await verify_setup_action(data, request, user, db, replacement=True)


@router.delete('/2fa/setup', status_code=204)
async def cancel_setup(data: schemas.CancelSetupRequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'operativo', 'recovery')
    async def action(current, session):
        await factor.cancelar_setup(db, current, session, data.desafio_id)
        await db.commit()
        return Response(status_code=204, headers={'Cache-Control': 'no-store'})
    return await sensitive(db, request, user, action)


async def recovery_action(data, request, user, db, *, assisted=False):
    auth.exigir_proposito(request.state.auth_session, 'mfa_pending')
    async def action(current, previous):
        await factor.recuperar(db, current, previous, password=data.password, code=data.autorizacion_recuperacion if assisted else data.codigo_recuperacion, assisted=assisted)
        return await transition(db, current, await auth.crear_sesion(db, current, 'recovery'))
    return await sensitive(db, request, user, action)


@router.post('/2fa/recovery')
async def recover(data: schemas.RecoveryRequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await recovery_action(data, request, user, db)


@router.post('/2fa/assisted-recovery')
async def assisted_recover(data: schemas.AssistedRecoveryRequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    return await recovery_action(data, request, user, db, assisted=True)


@router.post('/2fa/recovery-codes/regenerate')
async def regenerate(data: schemas.PruebaTOTP, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'operativo')
    async def action(current, previous):
        codes = await factor.regenerar(db, current, password=data.password, codigo_totp=data.codigo_totp)
        return await transition(db, current, await auth.crear_sesion(db, current, 'operativo', mfa_at=clock.now()), codes=codes)
    return await sensitive(db, request, user, action)


@router.post('/2fa/disable')
async def disable(data: schemas.Disable2FARequest, request: Request, user: Usuario = Depends(get_auth_user), db: AsyncSession = Depends(get_db)):
    auth.exigir_proposito(request.state.auth_session, 'operativo', 'mfa_pending')
    async def action(current, session):
        await factor.desactivar(db, current, password=data.password, codigo_totp=data.codigo_totp, codigo_recuperacion=data.codigo_recuperacion)
        await db.commit()
        response = no_store({'estado': 'sesion_finalizada', 'totp_habilitado': False})
        auth.borrar_cookie(response)
        return response
    return await sensitive(db, request, user, action)


@router.post('/register', response_model=UsuarioResponse)
async def register_user(user_data: UsuarioCreate, background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.routers.usuarios import crear_usuario
    return await crear_usuario(user_data, background_tasks=background_tasks, current_user=current_user, db=db)
