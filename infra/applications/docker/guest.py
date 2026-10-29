"""Fixed guest program. Input is private stdin; stdout is a closed result only."""
import base64
import errno
import http.client
import json
import os
from pathlib import Path
import re
import selectors
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID

if __package__:
    from .contract import application_arguments,volume_name


class InstallError(Exception):
    def __init__(self,code='UNCONFIRMED'):self.code=code


def run_command(args,*,capture=False,environment=None):
    env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8',**(environment or {})}
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=sys.stderr,env=env)
    output=bytearray();deadline=time.monotonic()+600
    try:
        if capture:
            os.set_blocking(process.stdout.fileno(),False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic()>=deadline:raise InstallError()
                    for key,_ in selector.select(.25):
                        chunk=os.read(key.fd,65536)
                        if not chunk:selector.unregister(key.fileobj)
                        output.extend(chunk)
                        if len(output)>4*1024**2:raise InstallError()
        code=process.wait(timeout=max(.01,deadline-time.monotonic()))
        if code!=0:raise InstallError('DEPENDENCY_UNAVAILABLE')
        return bytes(output)
    except (OSError,subprocess.SubprocessError):raise InstallError() from None
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=2)
        if capture:process.stdout.close()


class DockerGuest:
    def __init__(self,request,*,root=Path('/'),run=run_command):
        self.request,self.root,self.run=request,Path(root),run
        self.identity=request['identity'];self.configuration=request['configuration']
        UUID(self.identity['resource_uuid'])
        if not re.fullmatch(r'[a-f0-9]{64}',self.identity['configuracion_sha256']):raise InstallError()
        self.name='nap-'+UUID(self.identity['resource_uuid']).hex
        self.edge_name=self.name+'-edge'
        self.directory=self.root/'etc/nap'
        self.cli=self.root/'run/nap-docker-cli'

    def private_write(self,path,data):
        path=Path(path)
        if not path.is_relative_to(self.root):raise InstallError()
        parent=self.root
        for part in path.relative_to(self.root).parts[:-1]:
            parent=parent/part
            if not parent.exists():parent.mkdir(mode=0o700)
            info=parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:raise InstallError()
        if path.parent.resolve()!=path.parent or path.parent.stat().st_mode&0o077:raise InstallError()
        if path.exists() or path.is_symlink():
            info=path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_mode&0o077
                    or info.st_uid!=os.geteuid() or info.st_size!=len(data) or path.read_bytes()!=data):raise InstallError()
            return
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as target:target.write(data);target.flush();os.fsync(target.fileno())

    def marker(self):
        expected={key:self.identity[key] for key in ('cluster_uuid','resource_uuid','nonce_sha256','configuracion_sha256')}
        self.private_write(self.directory/'instance.json',json.dumps(expected,sort_keys=True).encode())
        self.private_write(self.cli/'config.json',b'{"auths":{}}')

    def docker(self,args,*,capture=False,environment=None,config=None,timeout=None):
        command=['/usr/bin/docker','--config',str(config or self.cli),*args]
        if timeout is not None:command=['/usr/bin/timeout','--kill-after=2',str(timeout),*command]
        return self.run(command,capture=capture,environment=environment)

    def inspect(self,kind,name):
        raw=self.docker([kind,'inspect',name],capture=True)
        value=json.loads(raw)
        if type(value)is not list or len(value)!=1 or type(value[0])is not dict:raise InstallError()
        return value[0]

    def prepare(self):
        self.marker()
        expected=self.request['runtime']
        raw=self.run(['/usr/bin/dpkg-query','-W','-f','${binary:Package}=${Version}\n','docker.io','containerd','runc'],capture=True)
        packages=dict(line.split('=',1) for line in raw.decode().splitlines())
        if packages!={'docker.io':expected['docker'],'containerd':expected['containerd'],'runc':expected['runc']}:raise InstallError('DEPENDENCY_UNAVAILABLE')
        driver=json.loads(self.docker(['info','--format','{{json .Driver}}'],capture=True))
        security=json.loads(self.docker(['info','--format','{{json .SecurityOptions}}'],capture=True))
        fs=self.run(['/usr/bin/findmnt','--noheadings','--output','FSTYPE','/'],capture=True).decode().strip()
        if (driver!=expected['storage_driver'] or fs!='ext4'
                or not any('name=seccomp' in v for v in security) or not any('name=apparmor' in v for v in security)):raise InstallError()
        for name in ('docker.io','containerd','runc'):
            print(json.dumps({'event':'package','name':name,'status':'installed'}),file=sys.stderr,flush=True)

    def pull(self):
        image=self.configuration['imagen'];registry=self.request['registry']
        host=image['repositorio'].split('/')[0]
        if registry['reference_host']!=host:raise InstallError('IDENTITY_MISMATCH')
        if registry.get('ca_pem'):
            if not re.fullmatch(r'[a-z0-9.-]+(?::[1-9][0-9]{0,4})?',host):raise InstallError()
            self.private_write(self.root/'etc/docker/certs.d'/host/'ca.crt',registry['ca_pem'].encode())
        # Authentication is a private temporary file, never login flags/env/image.
        with tempfile.TemporaryDirectory(prefix='nap-pull-',dir=self.root/'run') as private:
            auth={}
            if registry.get('username') and registry.get('password'):
                encoded=base64.b64encode((registry['username']+':'+registry['password']).encode()).decode('ascii')
                auth={host:{'auth':encoded}}
            self.private_write(Path(private)/'config.json',json.dumps({'auths':auth}).encode())
            self.docker(['pull','--platform','linux/'+image['arquitectura'],image['repositorio']+'@'+image['manifest_digest']],config=private)
        info=self.inspect('image',image['repositorio']+'@'+image['manifest_digest'])
        if (info['Id'] not in {image['config_digest'],image['manifest_digest']} or info['Os']!='linux' or info['Architecture']!=image['arquitectura']
                or not set((info.get('Config') or {}).get('Volumes') or {})<=set(self.configuration['persistencia'])):raise InstallError()
        if self.configuration['access']['tipo']=='tcp':return
        edge=self.request['edge']
        self.docker(['pull','--platform','linux/'+edge['arquitectura'],edge['repositorio']+'@'+edge['manifest_digest']])
        if self.inspect('image',edge['repositorio']+'@'+edge['manifest_digest'])['Id'] not in {edge['config_digest'],edge['manifest_digest']}:raise InstallError()

    def configure(self):
        if self.configuration['access']['tipo']=='tcp':
            self.database_tls()
            self.configure_volumes()
            return
        material=self.request['tls'];edge_dir=self.directory/'edge'
        self.private_write(edge_dir/'tls/server.crt',(material['certificate_pem']+material['ca_pem']).encode())
        self.private_write(edge_dir/'tls/server.key',material['private_key_pem'].encode())
        caddy='''{
 admin off
 auto_https off
 persist_config off
}
https://:8443 {
 tls /run/nap-tls/server.crt /run/nap-tls/server.key
 reverse_proxy http://127.0.0.1:18080
}
'''
        self.private_write(edge_dir/'Caddyfile',caddy.encode())
        self.configure_volumes()

    def database_tls(self):
        """Read-only TLS mount owned by mysql inside this guest, never shared."""
        directory=self.directory/'database-tls'
        if not directory.exists():directory.mkdir(mode=0o700)
        info=directory.lstat()
        if (directory.resolve()!=directory or not stat.S_ISDIR(info.st_mode)
                or info.st_mode&0o077 or info.st_uid not in {os.geteuid(),999}):raise InstallError()
        material=self.request['tls']
        for name,value in {'ca.crt':material['ca_pem'],'server.crt':material['certificate_pem']+material['ca_pem'],
                'server.key':material['private_key_pem']}.items():
            path=directory/name;raw=value.encode()
            if path.exists() or path.is_symlink():
                info=path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid not in {os.geteuid(),999}
                        or info.st_mode&0o077 or path.read_bytes()!=raw):raise InstallError()
            else:
                descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(descriptor,'wb') as target:target.write(raw);target.flush();os.fsync(target.fileno())
            os.chown(path,999,999)
        os.chown(directory,999,999)

    def configure_volumes(self):
        for path in self.configuration['persistencia']:
            name=volume_name(self.identity['resource_uuid'],path)
            names=self.docker(['volume','ls','--format','{{json .Name}}'],capture=True).decode().splitlines()
            if name not in [json.loads(v) for v in names]:
                self.docker(['volume','create','--driver','local','--label','nap.resource_uuid='+self.identity['resource_uuid'],name])
            volume=self.inspect('volume',name)
            if volume['Driver']!='local' or volume.get('Options') or volume['Labels'].get('nap.resource_uuid')!=self.identity['resource_uuid']:raise InstallError('IDENTITY_MISMATCH')

    def start(self):
        values=self.request['private_values']
        if set(values)!={s['nombre'] for s in self.configuration['secretos']}:raise InstallError()
        environment={**self.configuration['variables'],**values}
        if any(type(v)is not str or '\x00'in v for v in environment.values()):raise InstallError()
        args=application_arguments(self.identity,self.configuration,self.request['resources'],tls_directory=str(self.directory/'database-tls'))
        self.docker(args,environment=environment)
        if self.configuration['access']['tipo']=='web':self.start_edge()
        self.verify_started()

    def start_edge(self):
        edge=self.request['edge'];edge_dir=self.directory/'edge'
        self.docker(['run','-d','--name',self.edge_name,'--pull=never','--restart=unless-stopped',
            '--network=host','--read-only','--cap-drop=ALL','--cap-add=NET_BIND_SERVICE','--security-opt=no-new-privileges:true',
            '--log-driver=none','--no-healthcheck','--pids-limit=64','--memory=128m','--memory-swap=128m',
            '--label=nap.resource_uuid='+self.identity['resource_uuid'],
            '--tmpfs','/data:rw,noexec,nosuid,size=16m','--tmpfs','/config:rw,noexec,nosuid,size=8m',
            '--tmpfs','/tmp:rw,noexec,nosuid,size=8m',
            '--mount','type=bind,source='+str(edge_dir/'Caddyfile')+',target=/etc/caddy/Caddyfile,readonly',
            '--mount','type=bind,source='+str(edge_dir/'tls')+',target=/run/nap-tls,readonly',
            '--entrypoint=caddy',edge['repositorio']+'@'+edge['manifest_digest'],
            'run','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
    def verify_started(self):
        app=self.inspect('container',self.name)
        if (not app['State']['Running'] or app['Image'] not in {self.configuration['imagen']['config_digest'],self.configuration['imagen']['manifest_digest']}
                or app['Config']['Labels'].get('nap.resource_uuid')!=self.identity['resource_uuid']
                or app['HostConfig']['LogConfig']['Type']!='none'
                or app.get('AppArmorProfile') in (None,'','unconfined')
                or app['Config'].get('Healthcheck',{}).get('Test')!=['NONE']):raise InstallError()
        mounts={v['Destination']:v for v in app['Mounts']}
        if self.configuration['access']['tipo']=='tcp':
            tls=mounts.pop('/run/nap-tls',{})
            if (tls.get('Type')!='bind' or tls.get('Source')!=str(self.directory/'database-tls')
                    or tls.get('RW') is not False):raise InstallError()
        if set(mounts)!=set(self.configuration['persistencia']):raise InstallError()
        for path,mount in mounts.items():
            if mount.get('Type')!='volume' or mount.get('Name')!=volume_name(self.identity['resource_uuid'],path):raise InstallError()

    def probe(self):
        if self.configuration['access']['tipo']=='tcp':return self.probe_database()
        probe=self.configuration['access']['probe'];deadline=time.monotonic()+90
        context=ssl.create_default_context(cadata=self.request['tls']['ca_pem'])
        while time.monotonic()<deadline:
            connection=None
            try:
                plain=socket.create_connection(('127.0.0.1',8443),timeout=probe['timeout_segundos'])
                stream=context.wrap_socket(plain,server_hostname=self.request['network']['host'])
                connection=http.client.HTTPConnection('127.0.0.1',8443,timeout=probe['timeout_segundos']);connection.sock=stream
                connection.request('GET',probe['path'],headers={'Host':self.request['network']['host']+':8443','Accept-Encoding':'identity'})
                response=connection.getresponse()
                if response.status in probe['estados'] and len(response.read(65537))<=65536:return
            except (OSError,http.client.HTTPException):pass
            finally:
                if connection is not None:connection.close()
            time.sleep(1)
        raise InstallError('DEPENDENCY_UNAVAILABLE')

    def probe_database(self):
        deadline=time.monotonic()+120
        password=self.request['private_values']['MARIADB_PASSWORD']
        while time.monotonic()<deadline:
            try:
                self.verify_started()
                raw=self.docker(['exec','--env','MYSQL_PWD',self.name,'mariadb','--no-defaults',
                    '--protocol=tcp','--host='+self.request['network']['address'],'--port=3306','--user=docente',
                    '--database=catedra','--connect-timeout=5','--ssl-ca=/run/nap-tls/ca.crt',
                    '--ssl-verify-server-cert','--batch','--skip-column-names','--execute=SELECT 1'],
                    capture=True,environment={'MYSQL_PWD':password},timeout=15)
                if raw.strip()==b'1':return
            except InstallError:pass
            time.sleep(2)
        raise InstallError('DEPENDENCY_UNAVAILABLE')

    def execute(self):
        action=self.request['action']
        if action not in {'prepare','pull','configure','start','probe'}:raise InstallError()
        self.marker()
        getattr(self,action)()


def main():
    request={};code=None
    try:
        raw=sys.stdin.buffer.read(1048577)
        if len(raw)>1048576:raise InstallError()
        request=json.loads(raw)
        DockerGuest(request).execute()
    except InstallError as exc:code='UNCONFIRMED' if request.get('action')=='start' else exc.code
    except OSError as exc:code='NO_SPACE' if exc.errno==errno.ENOSPC else 'UNCONFIRMED'
    except Exception:code='UNCONFIRMED'
    identity=request.get('identity',{})
    print(json.dumps({'ok':code is None,'action':request.get('action'),
        'resource_uuid':identity.get('resource_uuid'),'configuracion_sha256':identity.get('configuracion_sha256'),
        'error_codigo':code}),flush=True)
    return 0 if code is None else 1


if __name__=='__main__':raise SystemExit(main())
