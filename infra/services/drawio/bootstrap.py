"""Draw.io preparado; perímetro por instancia y ningún paquete en bootstrap."""
from uuid import UUID
import ipaddress
import re
import time
if __package__:
    from infra.services.common import GuestError,GuestCommandError,bind_network,configure_console,install_tls,main,network_configuration
else:
    from common import GuestError,GuestCommandError,bind_network,configure_console,install_tls,main,network_configuration

DIRECTORY='etc/nap/drawio'
TOMCAT='opt/nap-drawio/tomcat'


def username(request):return 'nap_'+UUID(request['resource_uuid']).hex


def web_configuration(network):
    address=ipaddress.ip_address(network['address']);listen=f'[{address}]' if address.version==6 else str(address)
    allowed=''.join('    allow '+cidr+';\n' for cidr in network['client_cidrs'])
    return f'''server {{
    listen 127.0.0.1:443 ssl;
    listen {listen}:443 ssl;
    server_name {network['host']};
    if ($host != {network['host']}) {{ return 444; }}
    ssl_certificate /{DIRECTORY}/server.crt;
    ssl_certificate_key /{DIRECTORY}/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    allow 127.0.0.1;
{allowed}    deny all;
    auth_basic "NAP";
    auth_basic_user_file /{DIRECTORY}/htpasswd;
    access_log off;
    client_max_body_size 20m;
    location / {{
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Authorization "";
        proxy_pass http://127.0.0.1:8080;
    }}
}}
'''


class Drawio:
    parameters=['display_name']
    secret_fields=['access_password']

    def prepare(self,context):
        system=context.system;network=network_configuration(context.request);bind_network(context,network)
        password=context.request['secrets']['access_password']
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',password):raise GuestError('INVALID_REQUEST')
        context.step('tls',lambda:install_tls(system,network,DIRECTORY,owner='root:root'))
        context.step('console_configuration',lambda:configure_console(system))
        def perimeter():
            encoded=system.run(['/usr/bin/openssl','passwd','-6','-stdin'],input=password+'\n').strip()
            if not encoded.startswith('$6$'):raise GuestError('UNCONFIRMED')
            user=username(context.request)
            system.write(DIRECTORY+'/htpasswd',user+':'+encoded+'\n',mode=0o640)
            system.run(['/usr/bin/chown','root:www-data','/'+DIRECTORY+'/htpasswd'])
            system.write(DIRECTORY+'/probe.netrc','machine '+network['host']+' login '+user+' password '+password+'\n')
            # Nginx sólo necesita leer htpasswd; directorio/certificados siguen protegidos.
            system.run(['/usr/bin/chown','root:www-data','/'+DIRECTORY])
            system.path(DIRECTORY).chmod(0o750)
        context.step('perimeter',perimeter)
        def runtime_directories():
            # El saneamiento elimina logs, cachés y temporales; recrearlos vacíos.
            system.path('var/log/nginx').mkdir(parents=True,exist_ok=True,mode=0o755)
            paths=[]
            for name in ['logs','temp','work']:
                relative=TOMCAT+'/'+name
                system.path(relative).mkdir(parents=True,exist_ok=True,mode=0o750)
                paths.append('/'+relative)
            system.run(['/usr/bin/chown','napdrawio:napdrawio',*paths])
        context.step('runtime_directories',runtime_directories)
        def configure():
            system.write(TOMCAT+'/conf/server.xml','<Server port="-1"><Service name="Catalina"><Connector address="127.0.0.1" port="8080" protocol="HTTP/1.1" server="NAP" /><Engine name="Catalina" defaultHost="localhost"><Host name="localhost" appBase="webapps" unpackWARs="true" autoDeploy="false" /></Engine></Service></Server>\n',mode=0o644)
            system.write('etc/nginx/sites-enabled/nap-drawio.conf',web_configuration(network),mode=0o644)
            system.run(['/usr/sbin/nginx','-t'])
        context.step('web_configuration',configure)
        for service in ['nap-drawio.service','nginx.service']:
            for action in ['unmask','enable','start']:system.run(['/usr/bin/systemctl',action,service])

    def inspect(self,context):
        network=network_configuration(context.request);bind_network(context,network)
        endpoint='https://'+network['host']
        base=['/usr/bin/curl','--silent','--show-error','--noproxy','*','--max-time','10','--proto','=https',
            '--cacert','/'+DIRECTORY+'/ca.crt','--resolve',network['host']+':443:127.0.0.1']
        try:
            anonymous=context.system.run(base+['--output','/dev/null','--write-out','%{http_code}',endpoint],timeout=15)
            page=context.system.run(base+['--fail','--netrc-file','/'+DIRECTORY+'/probe.netrc',endpoint],timeout=15)
            ready=anonymous=='401' and ('draw.io' in page.lower() or 'diagrams.net' in page.lower()) and '<script' in page.lower()
        except GuestCommandError:ready=False
        return {'ready':ready,'bootstrap_completed':bool(context.state.get('completed')),'host':network['host'],
            'address':network['address'],'port':443,'endpoint':endpoint,'username':username(context.request),
            'checks':['drawio-status-v1'] if ready else []}

    def verify(self,context):
        deadline=time.monotonic()+(30 if context.request['action']=='bootstrap' else 0)
        while True:
            result=self.inspect(context)
            if result['ready']:return result
            if time.monotonic()>=deadline:raise GuestError('PROBE_FAILED')
            time.sleep(1)


if __name__=='__main__':main(Drawio())
