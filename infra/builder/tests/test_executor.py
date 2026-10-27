import pytest


def message(action, generation=1, operation='build'):
    return {'protocol':'nap-build-runner/1','ensayo_id':'11111111-1111-4111-8111-111111111111',
        'operation_id':operation,'generation':generation,'action':action,'recipe_id':'drawio-tomcat11-ubuntu-24.04-v1',
        'recipe_revision':'a'*40,'input_sha256':'b'*64,'input_ref':'inputs-prueba'}


def test_status_conserva_inputs_resueltos_del_trabajo_y_perfil_solo_completa_faltantes(tmp_path,monkeypatch):
    from infra.builder.executor import BuildExecutor
    from infra.builder import actions
    template={'recipe_ready':True,'recipe_revision':'a'*40,'input_ref':'plan-registrado','input_sha256':'b'*64}
    monkeypatch.setattr(actions,'profile',lambda root:template)
    ex=BuildExecutor(root=tmp_path)
    identity=message('status')['ensayo_id']
    with ex.locked(identity) as state:
        state['jobs']['resolve']={'status':'succeeded','result':{'input_ref':'c'*64,'input_sha256':'d'*64}}
    result=ex.execute(message('status',operation='resolve'))['result']
    assert result['recipe_ready'] is True
    assert (result['input_ref'],result['input_sha256'])==('c'*64,'d'*64)
    initial=ex.execute(message('status',operation='primera-consulta'))['result']
    assert initial['input_ref']=='plan-registrado' and initial['input_sha256']=='b'*64


def test_construccion_tiene_namespace_de_montajes_y_grupo_de_procesos_propios(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from infra.builder import actions,executor
    calls=[]
    monkeypatch.setattr(actions,'profile',lambda root:{'recipe_ready':True})
    def start(argv,**kwargs):
        calls.append((argv,kwargs));return SimpleNamespace(pid=1234)
    monkeypatch.setattr(executor.subprocess,'Popen',start)
    result=executor.BuildExecutor(root=tmp_path).execute(message('build'))
    argv,options=calls[0]
    assert result['status']=='accepted'
    assert argv[:4]==['/usr/bin/unshare','--mount','--propagation','private']
    assert argv[-3:]==['--work',message('build')['ensayo_id'],'build']
    assert options['start_new_session'] is True


def test_cancel_antes_de_build_y_reinicio(tmp_path):
    from infra.builder.executor import BuildExecutor, BuildError
    effects=[]
    executor=BuildExecutor(root=tmp_path,handler=lambda request:effects.append(request) or {'ready':True})
    executor.execute(message('cancel',2,'cancel'))
    executor.execute(message('cleanup',2,'cleanup'))
    restarted=BuildExecutor(root=tmp_path,handler=lambda request:effects.append(request) or {})
    with pytest.raises(BuildError):restarted.execute(message('build',1))
    with pytest.raises(BuildError):restarted.execute(message('build',3))
    assert not effects


def test_idempotencia_y_status_tras_perder_confirmacion(tmp_path):
    from infra.builder.executor import BuildExecutor, BuildError
    calls=[]
    ex=BuildExecutor(root=tmp_path,handler=lambda r:calls.append(r) or {'image_sha256':'c'*64})
    first=ex.execute(message('build'));again=ex.execute(message('build'))
    assert first['job_id']==again['job_id'] and len(calls)==1
    assert ex.execute(message('status'))['status']=='succeeded'
    bad=message('build');bad['input_sha256']='c'*64
    with pytest.raises(BuildError):ex.execute(bad)


def test_estado_running_no_reejecuta_tras_caida(tmp_path):
    from infra.builder.executor import BuildExecutor
    def uncertain(_):raise TimeoutError()
    ex=BuildExecutor(root=tmp_path,handler=uncertain)
    assert ex.execute(message('build'))['status']=='unknown'
    calls=[]
    ex=BuildExecutor(root=tmp_path,handler=lambda r:calls.append(r) or {})
    assert ex.execute(message('build'))['status']=='unknown' and not calls


def test_cancel_persiste_cierre_si_detencion_falla(tmp_path,monkeypatch):
    from infra.builder.executor import BuildExecutor,BuildError
    ex=BuildExecutor(root=tmp_path,handler=lambda r:{})
    def fail(state):raise BuildError('process_unknown')
    monkeypatch.setattr(ex,'stop',fail)
    with pytest.raises(BuildError):ex.execute(message('cancel',2,'cancel'))
    other=BuildExecutor(root=tmp_path,handler=lambda r:{})
    assert other.execute(message('status'))['closed'] is True
    with pytest.raises(BuildError):other.execute(message('build',3))


def test_cancel_reintento_completa_detencion_tras_confirmacion_perdida(tmp_path,monkeypatch):
    from infra.builder.executor import BuildExecutor,BuildError
    ex=BuildExecutor(root=tmp_path,handler=lambda r:{})
    original=ex.stop
    monkeypatch.setattr(ex,'stop',lambda state:(_ for _ in ()).throw(BuildError('uncertain')))
    with pytest.raises(BuildError):ex.execute(message('cancel',2,'cancel'))
    monkeypatch.setattr(ex,'stop',original)
    result=ex.execute(message('cancel',2,'cancel'))
    assert result['closed'] and result['status']=='cancelled'
    assert ex.execute(message('cleanup',2,'cleanup'))['status']=='succeeded'
