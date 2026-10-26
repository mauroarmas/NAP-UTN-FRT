import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location('campus_demo',
    Path(__file__).parents[1] / 'fixtures' / 'campus-demo' / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_persistence_survives_reopening_and_isolates_instances(tmp_path):
    first = app.NoteStore(tmp_path / 'first')
    second = app.NoteStore(tmp_path / 'second')
    status, _, body = app.dispatch('POST', '/api/note', b'{"note":"Una nota"}', first)
    assert status == 200
    assert json.loads(body)['saved']
    assert app.NoteStore(tmp_path / 'first').read() == 'Una nota'
    assert second.read() == ''
    assert app.dispatch('GET', '/health', b'', first)[0] == 200


def test_invalid_input_cannot_replace_persistent_note(tmp_path):
    store = app.NoteStore(tmp_path / 'data')
    store.write('original')
    for value in [b'{"note":null}', b'{"note":{},"path":"/etc/passwd"}',
                  json.dumps({'note': 'x' * 2001}).encode(), b'broken', b'[]']:
        assert app.dispatch('POST', '/api/note', value, store)[0] == 422
    assert store.read() == 'original'


def test_note_is_json_data_not_interpolated_html(tmp_path):
    store = app.NoteStore(tmp_path / 'data')
    attack = '</textarea><script>alert(1)</script>'
    store.write(attack)
    assert attack.encode() not in app.dispatch('GET', '/', b'', store)[2]
    assert json.loads(app.dispatch('GET', '/api/note', b'', store)[2])['note'] == attack
    assert app.dispatch('GET', '/other', b'', store)[0] == 404
