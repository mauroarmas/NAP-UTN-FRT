"""Errores de dominio públicos sin trazas ni entradas sensibles."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error(status, codigo, mensaje, *, reintentable=False, headers=None, **extra):
    return HTTPException(status_code=status, detail={
        'codigo': codigo, 'mensaje': mensaje, 'reintentable': reintentable, **extra,
    }, headers=headers)


def install_error_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request, exc):
        defaults = {400: 'datos_invalidos', 401: 'sesion_invalida', 403: 'sin_permisos',
                    404: 'no_encontrado', 405: 'metodo_no_permitido', 409: 'conflicto',
                    413: 'contenido_demasiado_grande', 422: 'datos_invalidos', 502: 'infraestructura_no_verificable'}
        if isinstance(exc.detail, dict) and 'codigo' in exc.detail:
            detail = {'reintentable': False, **exc.detail}
        else:
            message = str(exc.detail) if exc.status_code < 500 else 'No se pudo confirmar la infraestructura. Reintentá más tarde.'
            detail = {'codigo': defaults.get(exc.status_code, 'solicitud_rechazada'),
                      'mensaje': message, 'reintentable': exc.status_code == 502}
        return JSONResponse(status_code=exc.status_code, content={'detail': detail},
                            headers={'Cache-Control': 'no-store', **(exc.headers or {})})

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request, exc):
        messages = {'extra_forbidden': 'Campo no permitido', 'missing': 'Campo obligatorio',
                    'int_type': 'Debe ser un entero', 'greater_than_equal': 'Valor inferior al mínimo permitido',
                    'less_than_equal': 'Valor superior al máximo permitido'}
        fields = {'.'.join(str(p) for p in item['loc'] if p != 'body'):
                  messages.get(item['type'], 'Formato o valor inválido') for item in exc.errors()}
        return JSONResponse(status_code=422, content={'detail': {
            'codigo': 'datos_invalidos', 'mensaje': 'Revisá los campos indicados',
            'reintentable': False, 'campos': fields,
        }}, headers={'Cache-Control': 'no-store'})
