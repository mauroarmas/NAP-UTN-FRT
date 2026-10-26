"""Completar un plan institucional con inventario observado y fuentes fijadas.

Se usa en el entorno descartable de resolución, antes de registrar el catálogo
privado del builder. No publica ni afirma haber comprobado el editor.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path


def sha256(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def resolve(plan,resolution,*,drawio_version,war_path,tomcat_version,tomcat_path):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',drawio_version) or not re.fullmatch(r'11\.0\.[0-9]+',tomcat_version):
        raise ValueError('Versiones exactas requeridas')
    if resolution['product']!='drawio' or not resolution['package_lock']:raise ValueError('Inventario Draw.io requerido')
    result=deepcopy(plan)
    result['package_lock']=deepcopy(resolution['package_lock'])
    components=deepcopy(resolution['runtime']['components'])
    if not components['java']['version'].startswith('21'):raise ValueError('JRE 21 requerido')
    components.update(drawio={'version':drawio_version,'source_sha256':sha256(war_path)},
        tomcat={'version':tomcat_version,'source_sha256':sha256(tomcat_path)})
    result['manifest']['schema_version']='1.1'
    result['manifest']['runtime']={'packages':deepcopy(resolution['runtime']['packages']),'components':components}
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['plan','resolution','drawio-version','war-path','tomcat-version','tomcat-path','output']:parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    result=resolve(json.loads(Path(args.plan).read_text()),json.loads(Path(args.resolution).read_text()),
        drawio_version=args.drawio_version,war_path=args.war_path,tomcat_version=args.tomcat_version,tomcat_path=args.tomcat_path)
    with Path(args.output).open('x') as output:json.dump(result,output,sort_keys=True,indent=2)


if __name__=='__main__':main()
