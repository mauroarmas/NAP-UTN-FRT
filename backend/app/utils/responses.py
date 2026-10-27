from fastapi.responses import JSONResponse


def respuesta_decision(result):
    headers = {'Cache-Control': 'no-store'}
    if result.replayed:
        headers['Idempotency-Replayed'] = 'true'
    if result.status_code == 202 and result.resultado.get('cambio_consola_id'):
        headers['Location'] = '/api/v1/admin/cambios-consola/' + result.resultado['cambio_consola_id']
    if result.status_code == 202 and result.resultado.get('operation_id'):
        headers['Location'] = '/api/v1/operaciones/' + result.resultado['operation_id']
        headers['Retry-After'] = '2'
    return JSONResponse(status_code=result.status_code, content=result.resultado, headers=headers)
