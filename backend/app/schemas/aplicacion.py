"""Short catalog forms; infrastructure and executable overrides are server-owned."""
from typing import Literal
import re

from pydantic import Field,field_validator,model_validator

from app.schemas.configuracion_despliegue import Closed,DeclaracionSecreto,ProbeHTTP,RESERVED,NAME,FORBIDDEN_TARGETS


class ConfigurarAplicacion(Closed):
    origen:Literal['imagen_docker']='imagen_docker'
    imagen:str=Field(min_length=1,max_length=512)
    puerto:int=Field(ge=1,le=65535)
    modelo_servicio:Literal['saas','paas']|None=None
    variables:dict[str,str]=Field(default_factory=dict,max_length=20)
    secretos:list[DeclaracionSecreto]=Field(default_factory=list,max_length=20)
    persistencia:list[str]=Field(default_factory=list,max_length=8)
    ruta_salud:str=Field(default='/',min_length=1,max_length=512)
    websocket:bool=False

    @model_validator(mode='after')
    def options(self):
        ProbeHTTP(tipo='http',path=self.ruta_salud,estados=[200],timeout_segundos=10)
        names=list(self.variables)+[s.nombre for s in self.secretos]
        if (len(names)>20 or len(names)!=len(set(names)) or any(not re.fullmatch(NAME,n) or n in RESERVED or n.startswith(('LD_','NAP_','BASH_FUNC_')) for n in names)):
            raise ValueError('Revisá las variables y los datos privados declarados')
        if any(name.lower() in {'password','contraseña','secrets','credenciales','token','nonce','app_key','totp_secret'} for name in self.variables):
            raise ValueError('Declaralos como datos privados, sin incluir su valor en el catálogo')
        if any('\x00' in v or len(v.encode())>4096 for v in self.variables.values()):raise ValueError('Variable inválida')
        if len(self.persistencia)!=len(set(self.persistencia)):raise ValueError('Carpeta duplicada')
        for p in self.persistencia:
            if (not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',p) or len(p)>255
                    or any(s in {'.','..'} for s in p.split('/'))
                    or any(p==f or p.startswith(f+'/') for f in FORBIDDEN_TARGETS)):raise ValueError('Carpeta no admitida')
        return self


class AgregarAplicacion(ConfigurarAplicacion):
    nombre:str=Field(min_length=1,max_length=100)
    descripcion:str|None=Field(default=None,max_length=2000)

    @field_validator('nombre',mode='before')
    @classmethod
    def name(cls,value):
        return value.strip() if isinstance(value,str) else value


class RevisarAplicacion(ConfigurarAplicacion):
    revision_esperada:int=Field(ge=1)
