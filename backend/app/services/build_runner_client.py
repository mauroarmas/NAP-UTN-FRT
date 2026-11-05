"""Transporte cerrado de construcción: hostkey fija, sin shell ni secretos en salida."""
import asyncio
import json
from uuid import UUID
from app.config import get_settings
from app.schemas.build_runner import BuildRequest,PROTOCOL
from app.schemas.guest_runner import RunnerError
from app.services.guest_runner_client import GuestRunnerClient, _destination


class BuildRunnerClient(GuestRunnerClient):
    def __init__(self,*,hosts=None,start_process=None):
        super().__init__(config={},start_process=start_process,timeout_seconds=10)
        self.hosts=hosts if hosts is not None else get_settings().builder_hosts

    async def execute(self,request,*,host_id):
        try:
            request=BuildRequest.model_validate(request).model_dump(mode='json',exclude_none=True)
            entry=self.hosts[host_id]
            entry=entry.model_dump() if hasattr(entry,'model_dump') else entry
            # El perfil también contiene presupuesto/revisión, que no son opciones SSH.
            destination={key:entry[key] for key in ('host','user','port','private_key_path','known_hosts_path')}
            host,user,port,key,known=_destination(destination)
        except (ValueError,KeyError,TypeError):raise RunnerError('INVALID_REQUEST') from None
        argv=['/usr/bin/ssh','-F','/dev/null','-T','-i',key,'-p',str(port),'-l',user]
        for option in ['BatchMode=yes','StrictHostKeyChecking=yes','IdentitiesOnly=yes','IdentityAgent=none',
            'UserKnownHostsFile='+known,'GlobalKnownHostsFile=/dev/null','ProxyCommand=none','ProxyJump=none',
            'PermitLocalCommand=no','PasswordAuthentication=no','ClearAllForwardings=yes','RequestTTY=no','ConnectTimeout=3']:
            argv+=['-o',option]
        argv+=['--',host,'nap-build-runner']
        raw=json.dumps(request,sort_keys=True,separators=(',',':')).encode()
        process=None
        try:
            async with asyncio.timeout(10):
                process=await self.start_process(*argv,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,limit=262145,start_new_session=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
                # Método de intercambio existente limita stdout a 64KiB: más estricto que contrato.
                output=await self._exchange(process,raw)
                if process.returncode:raise RunnerError('BUILDER_UNAVAILABLE')
                value=json.loads(output)
                allowed={'protocol','operation_id','generation','job_id','status','max_generation','closed','result','observed_at'}
                if (not isinstance(value,dict) or set(value)!=allowed or value['protocol']!=PROTOCOL
                    or value['operation_id']!=request['operation_id'] or value['generation']!=request['generation']
                    or value['status'] not in {'accepted','running','succeeded','failed','cancelled','not_found','unknown'}
                    or type(value['closed']) is not bool or type(value['max_generation']) is not int
                    or not isinstance(value['observed_at'],str) or not isinstance(value['result'],dict)):
                    raise RunnerError('INVALID_RESPONSE')
                return value
        except (TimeoutError,OSError,ValueError,TypeError):raise RunnerError('UNCONFIRMED') from None
        finally:await self._stop(process)
