"""Comprobar un paquete antes de publicarlo desde la UI administrativa.

La antigua publicación específica del laboratorio está retirada. Este comando
es de sólo lectura: no abre DB/PVE, no asigna identidades ni publica ofertas.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.schemas.evidencia import canonical, parse_document
from app.schemas.definicion import validar_manifest
from app.services.evidencia_service import BASE_CHECKS
from app.utils.clock import clock


def verificar_paquete(manifest, evidence, *, cluster_uuid, definition_id):
    validar_manifest(manifest)
    evidence = parse_document(canonical(evidence).encode())
    result, reference = evidence['resultado'], manifest['validation']
    required = BASE_CHECKS | ({'unique_secrets'} if manifest['product'] != 'linux' else set())
    if manifest['product'] == 'bookstack':
        required |= {'reader_permissions_and_revocation'}
    observed = datetime.fromisoformat(evidence['observado_at'].replace('Z','+00:00'))
    if (evidence['tipo'] != 'validacion_definicion' or evidence['entorno'] != 'real'
        or result['definicion_id'] != str(UUID(definition_id))
        or result['cluster_uuid'] != str(UUID(cluster_uuid)) or reference['cluster_uuid'] != result['cluster_uuid']
        or result['definition_key'] != manifest['definition_key'] or result['definition_version'] != manifest['definition_version']
        or result['image_sha256'] != manifest['image']['sha256']
        or result['recipe_sha256'] != manifest['preparation']['bundle_sha256']
        or reference['evidence_sha256'] != hashlib.sha256(canonical(evidence).encode()).hexdigest()
        or reference['instances_tested'] != len(result['instancias'])
        or sorted(reference['pve_versions']) != sorted(result['pve_versions'])
        or set(reference['checks']) != set(result['checks']) or not required <= set(result['checks'])
        or observed > clock.now() or observed != datetime.fromisoformat(reference['validated_at'].replace('Z','+00:00'))):
        raise ValueError('Paquete inconsistente o aceptación real incompleta')
    return {'definition_key':manifest['definition_key'], 'definition_version':manifest['definition_version'],
        'resultado':'coherencia_local_comprobada', 'publicado':False,
        'mensaje':'Registrar/validar/publicar con la cuenta administradora en Definiciones; este comando no acredita los ensayos ni su registro en DB.'}


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 65536: raise ValueError('Archivo demasiado grande')
    def unique(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError('Clave duplicada')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ['manifest','evidence','cluster-uuid','definition-id']:
        parser.add_argument('--'+field, required=True)
    args = parser.parse_args()
    try:
        result = verificar_paquete(read_json(args.manifest),read_json(args.evidence),
            cluster_uuid=args.cluster_uuid,definition_id=args.definition_id)
    except Exception:
        print('Paquete no comprobado. Revisar manifiesto, evidencia, identidad y hashes; no se realizaron cambios.')
        return 2
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
