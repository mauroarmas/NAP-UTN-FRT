import json

import pytest

from app.config import settings_from_file


def private(path,value):
    path.write_text(value if isinstance(value,str) else json.dumps(value))
    path.chmod(0o600)
    return path


def test_private_config_uses_explicit_values_without_reading_dotenv(tmp_path,monkeypatch):
    appdir=tmp_path/'app';appdir.mkdir()
    (tmp_path/'.env').write_text('SECRET_KEY=dotenv-must-not-be-read\n')
    monkeypatch.chdir(appdir)
    config=settings_from_file(private(tmp_path/'config.json',{'secret_key':'file-private-value','app_debug':False}))
    assert config.secret_key=='file-private-value' and not config.app_debug
    assert 'file-private-value' not in repr(config)


@pytest.mark.parametrize('kind',['permissions','symlink','duplicate','unknown','type','nonfinite'])
def test_unsafe_or_invalid_private_file_never_prints_its_contents(tmp_path,kind):
    marker='private-value-must-not-appear'
    path=private(tmp_path/'config.json',{'secret_key':marker})
    if kind=='permissions': path.chmod(0o644)
    if kind=='symlink':
        other=tmp_path/'link';other.symlink_to(path);path=other
    if kind=='duplicate': private(path,'{"secret_key":"'+marker+'","secret_key":"duplicate"}')
    if kind=='unknown': private(path,{'secret_key':marker,'unsupported':True})
    if kind=='type': private(path,{'database_url':{'password':marker}})
    if kind=='nonfinite': private(path,'{"secret_key":"'+marker+'","smtp_port":NaN}')
    with pytest.raises(RuntimeError) as exc: settings_from_file(path)
    assert marker not in str(exc.value) and 'Configuración privada inválida' in str(exc.value)


def test_missing_private_file_fails_before_executing_server_or_migration(monkeypatch,capsys):
    from scripts.iniciar_operativo import main
    monkeypatch.delenv('NAP_SETTINGS_FILE',raising=False)
    monkeypatch.setattr('sys.argv',['iniciar_operativo','api'])
    def forbidden(*args): raise AssertionError('No ejecutar procesos sin configuración válida')
    monkeypatch.setattr('os.execv',forbidden)
    assert main()==1
    assert capsys.readouterr().err
