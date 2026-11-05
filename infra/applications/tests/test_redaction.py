import base64
import json
from urllib.parse import quote

import pytest

from infra.applications.job.redaction import SecretRedactor, ClosedOutput, MASK, SUPPRESSED
from infra.applications.job.protocol import JobError


@pytest.mark.parametrize('secret', ['fixture-pass-011', 'contraseña-ñ-011', 'a"b\\c\nfixture'])
def test_registered_representations_are_hidden_at_every_byte_boundary(secret):
    forms = [secret, base64.b64encode(secret.encode()).decode(), quote(secret, safe=''),
             json.dumps(secret, ensure_ascii=True)[1:-1]]
    for form in forms:
        raw = ('antes ' + form + ' después').encode()
        for boundary in range(len(raw)+1):
            redactor = SecretRedactor([secret])
            result = redactor.feed(raw[:boundary]) + redactor.feed(raw[boundary:], final=True)
            assert form not in result and MASK in result
            assert result.startswith('antes ') and result.endswith(' después')


def test_terminal_sequences_split_across_chunks_cannot_hide_a_secret():
    redactor = SecretRedactor(['fixture-private'])
    parts = [b'fixt\x1b[3', b'1mure-pri\x1b]0;unsafe-title', b'\x07vate\x1b[0m']
    output = ''.join(redactor.feed(p) for p in parts) + redactor.feed(b'', final=True)
    assert 'fixture-private' not in output and '\x1b' not in output and 'unsafe-title' not in output
    assert MASK in output


def test_unknown_output_is_discarded_and_only_closed_profile_events_survive():
    output = ClosedOutput(['fixture-private'], packages={'mariadb-server'})
    assert output.feed('stdout', b'password=fixture-private\n') == [SUPPRESSED]
    assert output.feed('stdout', b'other unknown output\n') == []
    # EOF flushes the bounded redaction tail, not the raw installer text.
    lines = output.feed('stdout', b'{"event":"package","name":"mariadb-server","status":"installed"}\n', final=True)
    assert lines == ['Paquete instalado: mariadb-server.']
    error = ClosedOutput([])
    assert error.feed('stderr', b'{"event":"phase","phase":"instalacion","message":"unregistered-secret"}\n', final=True) == [SUPPRESSED]


def test_utf8_controls_and_bidi_are_never_returned_to_the_console():
    redactor = SecretRedactor([])
    raw = 'Instalación\u202e\x00\x1b[31m lista\x1b[0m\r\n'.encode()
    result = ''.join(redactor.feed(bytes([b])) for b in raw) + redactor.feed(b'', final=True)
    assert result == 'Instalación lista\n'


def test_memory_is_bounded_and_unknown_long_lines_do_not_accumulate():
    output = ClosedOutput(['fixture-private'])
    result = []
    for _ in range(100): result += output.feed('stderr', b'x'*65536)
    result += output.feed('stderr', b'', final=True)
    assert result == [SUPPRESSED]
    assert output.pending_bytes <= 8192
    with pytest.raises(JobError): SecretRedactor(['x'*4097])
    with pytest.raises(JobError): output.feed('stdin', b'not-a-console')
    with pytest.raises(JobError): output.feed('stdout', b'x'*65537)


def test_redactor_configuration_cannot_change_after_output_starts():
    redactor = SecretRedactor(['one-secret'])
    redactor.feed(b'output')
    with pytest.raises(JobError): redactor.register('late-secret')


def test_truncated_secret_prefix_is_suppressed_when_process_exits():
    redactor = SecretRedactor(['fixture-private-value'])
    assert redactor.feed(b'prefix fixture-pri', final=True) == 'prefix ' + MASK
