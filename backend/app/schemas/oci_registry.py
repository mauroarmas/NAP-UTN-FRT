"""Institutional registry destinations; never supplied by the catalog form."""
from typing import Literal
from urllib.parse import urlsplit
import ipaddress
import re
from pathlib import PurePosixPath

from pydantic import BaseModel,ConfigDict,Field,model_validator


class Endpoint(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    host:str=Field(min_length=1,max_length=253)
    port:int=Field(default=443,ge=1,le=65535)
    addresses:list[str]=Field(default_factory=list,max_length=16)
    allow_public:bool=False
    ca_file:str=''

    @model_validator(mode='after')
    def closed(self):
        if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',v) for v in self.host.split('.')):raise ValueError('Registry endpoint unavailable')
        if not self.addresses and not self.allow_public:raise ValueError('Registry endpoint unavailable')
        for raw in self.addresses:
            value=ipaddress.IPv4Address(raw)
            if str(value)!=raw or value.is_loopback or value.is_link_local or value.is_unspecified or value.is_multicast or value.is_reserved:raise ValueError('Registry endpoint unavailable')
        return self


class RegistryProfile(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    registry:Endpoint
    reference_hosts:list[str]=Field(min_length=1,max_length=10)
    repository_prefixes:list[str]=Field(min_length=1,max_length=50)
    token_endpoint:Endpoint|None=None
    token_path:str='/token'
    token_service:str=''
    blob_endpoints:list[Endpoint]=Field(default_factory=list,max_length=10)
    credential_file:str=Field(default='',repr=False)

    @model_validator(mode='after')
    def closed(self):
        for host in self.reference_hosts:
            parsed=urlsplit('https://'+host)
            if parsed.hostname is None or parsed.netloc!=host or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Registry endpoint unavailable')
            if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',v) for v in parsed.hostname.split('.')):raise ValueError('Registry endpoint unavailable')
            if not re.fullmatch(r'[a-z0-9.-]+(?::[1-9][0-9]{0,4})?',host) or (parsed.port or 443)>65535:raise ValueError('Registry endpoint unavailable')
        for prefix in self.repository_prefixes:
            if prefix and not re.fullmatch(r'(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)+',prefix):raise ValueError('Registry repository unavailable')
        if (not re.fullmatch(r'/[A-Za-z0-9/_-]{0,100}',self.token_path)
                or not re.fullmatch(r'[A-Za-z0-9._:-]{0,253}',self.token_service)):raise ValueError('Registry token endpoint unavailable')
        if self.token_endpoint is not None and not self.token_service:raise ValueError('Registry token endpoint unavailable')
        if self.credential_file and (not self.credential_file.startswith('/') or '..' in PurePosixPath(self.credential_file).parts
                or '' in self.repository_prefixes):raise ValueError('Registry credential unavailable')
        return self
