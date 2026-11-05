"""Trabajos de construcción con cierre durable y rechazo de órdenes atrasadas.

El handler inyectado es sólo para pruebas. Producción despacha un proceso propio,
con entradas/recetas registradas por infraestructura, nunca shell del navegador.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import UUID


logger=logging.getLogger(__name__)


class BuildError(ValueError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def parse(raw):
    if len(raw)>65536:raise BuildError('request_too_large')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise BuildError('duplicate_key')
            result[key]=value
        return result
    try:
        value=json.loads(raw,object_pairs_hook=unique)
        from app.schemas.build_runner import BuildRequest
        return BuildRequest.model_validate(value).model_dump(mode='json',exclude_none=True)
    except (ValueError,TypeError,KeyError):raise BuildError('invalid_request') from None


class BuildExecutor:
    def __init__(self,*,root,handler=None):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink():raise BuildError('invalid_root')
        self.root=self.root.resolve()
        self.handler=handler

    def _path(self,identity):
        try:identity=str(UUID(identity))
        except (ValueError,TypeError):raise BuildError('invalid_identity') from None
        return self.root/(identity+'.json')

    @contextmanager
    def locked(self,identity):
        path=self._path(identity)
        lock=path.with_suffix('.lock')
        fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            if path.exists():
                if path.is_symlink():raise BuildError('invalid_state')
                state=json.loads(path.read_text())
            else:state={'max_generation':0,'closed':False,'jobs':{}}
            yield state
            temporary=path.with_suffix('.tmp')
            descriptor=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,'w') as handle:
                handle.write(canonical(state));handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,path)
            directory=os.open(self.root,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:os.close(fd)

    def response(self,request,state,job=None):
        stat=os.statvfs(self.root)
        result={'protocol':'nap-build-runner/1','operation_id':request['operation_id'],'generation':request['generation'],
            'job_id':request['operation_id'] if job else None,'status':job['status'] if job else 'not_found',
            'max_generation':state['max_generation'],'closed':state['closed'],'observed_at':datetime.now(timezone.utc).isoformat(),
            'result':{**(job.get('result',{}) if job else {}),'free_bytes':stat.f_bavail*stat.f_frsize}}
        if self.handler is None:
            from infra.builder.actions import profile
            # Los inputs resueltos de un trabajo prevalecen sobre la plantilla del host.
            for key,value in profile(self.root).items():
                result['result'].setdefault(key,value)
        return result

    def stop(self,state):
        for job in state['jobs'].values():
            if job['status'] not in {'accepted','running','unknown'}:continue
            pid=job.get('pid')
            if pid:
                # El PID debe conservar identidad registrada; no matar un PID reciclado.
                try:
                    cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
                    if b'--work' not in cmd or job['request']['ensayo_id'].encode() not in cmd:
                        raise BuildError('process_identity_unknown')
                    os.killpg(pid,signal.SIGKILL)
                    deadline=time.monotonic()+1
                    while time.monotonic()<deadline:
                        live=False
                        for status_path in Path('/proc').glob('[0-9]*/stat'):
                            try:fields=status_path.read_text().rsplit(')',1)[1].split()
                            except FileNotFoundError:continue
                            if fields[2]==str(pid) and fields[0]!='Z':live=True;break
                        if not live:break
                        time.sleep(0.01)
                    else:raise BuildError('process_stop_unconfirmed')
                except FileNotFoundError:
                    try:os.killpg(pid,0)
                    except ProcessLookupError:pass
                    else:raise BuildError('process_group_unknown')
                except ProcessLookupError:pass
            elif self.handler is None and job['status'] in {'running','unknown'}:
                raise BuildError('process_unknown')
            job['status']='cancelled'

    def execute(self,request):
        request=parse(canonical(request).encode())
        identity=request['ensayo_id'];action=request['action'];op=request['operation_id']
        logger.info('builder_operation ensayo_id=%s operation_id=%s action=%s generation=%s',identity,op,action,request['generation'])
        # Payload estable por operación; generación es control de ownership, no inputs.
        fingerprint=hashlib.sha256(canonical({k:v for k,v in request.items() if k!='generation'}).encode()).hexdigest()
        spawn=False
        with self.locked(identity) as state:
            if action=='status':return self.response(request,state,state['jobs'].get(op))
            if request['generation']<state['max_generation']:raise BuildError('stale_generation')
            if state['closed'] and action not in {'cancel','cleanup'}:raise BuildError('ensayo_closed')
            if request['generation']>state['max_generation']:
                if action!='cancel':self.stop(state)
                state['max_generation']=request['generation']
            if action=='cancel':
                # Cierre se persiste ANTES de intentar detener procesos.
                state['closed']=True
            elif action=='cleanup' and not state['closed']:raise BuildError('cancel_required')
            previous=state['jobs'].get(op)
            if previous:
                if previous['fingerprint']!=fingerprint:raise BuildError('operation_conflict')
                if action not in {'cancel','cleanup'} or previous['status'] in {'cancelled','succeeded'}:
                    return self.response(request,state,previous)
            job={'fingerprint':fingerprint,'request':request,'status':'accepted','result':{}}
            state['jobs'][op]=job
        # Cierre ya durable; crash en este punto nunca habilita un build atrasado.
        if action in {'cancel','cleanup'}:
            with self.locked(identity) as state:
                self.stop(state)
                job=state['jobs'][op]
                if action=='cleanup':
                    workspace=self.root/'work'/identity
                    if workspace.exists():
                        if workspace.is_symlink():raise BuildError('invalid_workspace')
                        import shutil
                        shutil.rmtree(workspace)
                    final=self.root/'artifacts'/identity
                    if final.exists():
                        job['result']['retained_bytes']=sum(p.stat().st_size for p in final.rglob('*') if p.is_file())
                job['status']='succeeded' if action=='cleanup' else 'cancelled'
                return self.response(request,state,job)
        if self.handler is not None:
            with self.locked(identity) as state:
                job=state['jobs'][op]
                try:job['result']=self.handler(request);job['status']='succeeded'
                except Exception:job['status']='unknown'
                return self.response(request,state,job)
        with self.locked(identity) as state:
            if state['closed'] or state['max_generation']!=request['generation']:raise BuildError('stale_generation')
            job=state['jobs'][op]
            process=subprocess.Popen(['/usr/bin/unshare','--mount','--propagation','private',
                sys.executable,str(Path(__file__).resolve()),'--root',str(self.root),'--work',identity,op],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':os.environ.get('PYTHONPATH','')})
            job['pid']=process.pid
            return self.response(request,state,job)

    def work(self,identity,operation):
        with self.locked(identity) as state:
            job=state['jobs'][operation];request=job['request']
            if state['closed'] or request['generation']!=state['max_generation']:
                job['status']='cancelled';return
            job['status']='running'
        try:
            from infra.builder.actions import execute_registered
            result=execute_registered(request,self.root)
            status='succeeded'
        except Exception:result={};status='failed'
        with self.locked(identity) as state:
            job=state['jobs'][operation]
            if state['closed'] or state['max_generation']!=request['generation']:
                job['status']='cancelled';return
            job.update(status=status,result=result)


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='/var/lib/nap-builder')
    parser.add_argument('--work',nargs=2)
    args=parser.parse_args()
    executor=BuildExecutor(root=args.root)
    if args.work:executor.work(*args.work);return
    try:
        request=parse(sys.stdin.buffer.read(65537));result=executor.execute(request)
        print(canonical(result))
    except BuildError:
        print(canonical({'error':'builder_request_rejected'}));raise SystemExit(1)


if __name__=='__main__':main()
