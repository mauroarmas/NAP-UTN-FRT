from uuid import UUID
import pytest
from tests.test_guest_runner_client import request


@pytest.fixture
def draw_system(tmp_path):
    from infra.services.common import GuestSystem
    class System(GuestSystem):
        def __init__(self):super().__init__(root=tmp_path);self.commands=[]
        def run(self,argv,*,input=None,**kwargs):
            assert not any(secret in str(arg) for secret in self.forbidden_arguments for arg in argv)
            self.commands.append(argv)
            if argv==['/usr/sbin/nginx','-t']:
                assert self.path('var/log/nginx').is_dir(),'Una imagen saneada no conserva el directorio de logs'
                for name in ['logs','temp','work']:
                    assert self.path('opt/nap-drawio/tomcat/'+name).is_dir()
            if argv[:2]==['/usr/bin/openssl','passwd']:return '$6$test$hash'
            if '-pubkey' in argv or '-pubout' in argv:return 'PUBLIC-KEY'
            if argv[0]=='/usr/bin/curl':return '401' if '--netrc-file' not in argv else '<title>draw.io</title><script src="js/app.min.js"></script>'
            return ''
    return System()


def test_bootstrap_privado_idempotente_sin_descargas(draw_system):
    from infra.services.common import run_product
    from infra.services.drawio.bootstrap import Drawio
    value=request()|{'parameters':{'display_name':'Diagramas'},'secrets':{'access_password':'drawio-secret-password-unique'},
        'infrastructure':{'host':'diagramas.example.edu','address':'10.50.0.110','client_cidrs':['10.50.0.0/24'],
            'tls_certificate':'CERTIFICATE-test-only','tls_private_key':'PRIVATE-KEY-test-only','tls_ca':'CA-CERTIFICATE-test-only'}}
    first=run_product(Drawio(),value,system=draw_system)
    second=run_product(Drawio(),value,system=draw_system)
    assert first['ready'] and first['username']=='nap_'+UUID(value['resource_uuid']).hex
    assert second['ready'] and sum(cmd[:2]==['/usr/bin/openssl','passwd'] for cmd in draw_system.commands)==1
    nginx=draw_system.read('etc/nginx/sites-enabled/nap-drawio.conf')
    assert 'auth_basic_user_file' in nginx and '127.0.0.1:8080' in nginx and 'deny all' in nginx
    assert 'address="127.0.0.1"' in draw_system.read('opt/nap-drawio/tomcat/conf/server.xml')
    assert not any('apt' in str(cmd) or 'wget' in str(cmd) for cmd in draw_system.commands)


def test_bootstrap_espera_el_arranque_del_editor_sin_repetir_preparacion(monkeypatch):
    from types import SimpleNamespace
    from infra.services.drawio import bootstrap
    now=[0];calls=[]
    monkeypatch.setattr(bootstrap.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(bootstrap.time,'sleep',lambda seconds:now.__setitem__(0,now[0]+seconds))
    def inspect(self,context):
        calls.append(context);return {'ready':len(calls)>=3}
    monkeypatch.setattr(bootstrap.Drawio,'inspect',inspect)
    assert bootstrap.Drawio().verify(SimpleNamespace(request={'action':'bootstrap'}))['ready']
    assert len(calls)==3 and now[0]==2
    calls.clear()
    with pytest.raises(bootstrap.GuestError):
        bootstrap.Drawio().verify(SimpleNamespace(request={'action':'verify'}))
    assert len(calls)==1 and now[0]==2
