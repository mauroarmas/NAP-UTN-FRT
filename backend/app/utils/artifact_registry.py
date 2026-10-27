"""Registro institucional recargable. Módulo de stdlib instalable en el runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def read_private_json(path,limit=262144):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('Ruta de registro inválida')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as handle:
        info=os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0,os.geteuid()} or info.st_mode&0o022 or info.st_size>limit:
            raise ValueError('Registro no controlado')
        raw=handle.read(limit+1)
        if len(raw)>limit:raise ValueError('Registro excesivo')
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Campo duplicado')
            result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=unique)


def entry_name(key):
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}:[0-9]+\.[0-9]+\.[0-9]+',key):raise ValueError('Identidad inválida')
    return hashlib.sha256(key.encode()).hexdigest()+'.json'


def lookup(settings,key):
    original=settings.service_artifacts.get(key)
    directory=getattr(settings,'artifact_registry_directory','')
    if not directory:return original
    try:
        document=read_private_json(Path(directory)/entry_name(key))
        if original is not None:raise ValueError('Registro duplicado')
        if document.get('key')!=key:raise ValueError('Registro de otra definición')
        return document['portal']
    except FileNotFoundError:return original


def all_entries(settings):
    result=dict(settings.service_artifacts)
    directory=getattr(settings,'artifact_registry_directory','')
    if directory:
        for path in sorted(Path(directory).glob('*.json')):
            document=read_private_json(path)
            key=document['key']
            if path.name!=entry_name(key) or key in result:raise ValueError('Registro duplicado o inválido')
            result[key]=document['portal']
    return result
