from copy import deepcopy
import hashlib
from uuid import uuid4
import pytest
from app.schemas.evidencia import canonical
from scripts.publicar_catalogo import verificar_paquete
from tests.service_helpers import manifest, definition_proof


@pytest.mark.parametrize('invalid',[None,'cluster','missing_check','digest','simulation'])
def test_verificacion_catalogo_no_inventa_resultados_ni_publica(invalid):
    value=manifest('bookstack')
    identity=str(uuid4())
    proof=definition_proof(identity,value)
    value['validation']['evidence_sha256']=hashlib.sha256(canonical(proof).encode()).hexdigest()
    original=deepcopy(proof)
    if invalid=='cluster': proof['resultado']['cluster_uuid']=str(uuid4())
    if invalid=='missing_check': proof['resultado']['checks'].remove('reader_permissions_and_revocation')
    if invalid=='digest': proof['resultado']['image_sha256']='0'*64
    if invalid=='simulation': proof['entorno']='simulado'
    args={'cluster_uuid':value['validation']['cluster_uuid'],'definition_id':identity}
    if invalid:
        with pytest.raises(Exception): verificar_paquete(value,proof,**args)
    else:
        result=verificar_paquete(value,proof,**args)
        assert result['publicado'] is False
        assert proof==original
