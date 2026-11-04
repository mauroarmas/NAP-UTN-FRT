"""El script de arranque reintenta sólo lo que falló y nunca reporta éxito si queda algo sin restaurar."""
from types import SimpleNamespace

from infra.applications.job import restore_boot


def runtime_factory(reports, calls):
    def factory():
        class Runtime:
            node = SimpleNamespace(restore_isolations=lambda: reports[min(len(calls) - 1, len(reports) - 1)])
            def __enter__(self): calls.append('open'); return self
            def __exit__(self, *args): return False
        return Runtime()
    return factory


def test_retries_failures_while_the_cluster_publishes_guests_and_keeps_what_was_restored():
    reports = [{'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': [{'resource_uuid': 'a', 'codigo': 'UNCONFIRMED'}]},
               {'restaurados': ['a'], 'vigentes': [], 'obsoletos': [], 'fallidos': []}]
    calls, pauses = [], []
    result = restore_boot.restore(runtime_factory(reports, calls), attempts=5, pause=2, sleep=pauses.append)
    assert result['restaurados'] == ['a'] and result['fallidos'] == [] and result['intentos'] == 2 and pauses == [2]


def test_definitive_failures_do_not_delay_the_boot_with_retries():
    stuck = {'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': [{'resource_uuid': 'a', 'codigo': 'PROFILE_UNAVAILABLE'}]}
    calls, pauses = [], []
    result = restore_boot.restore(runtime_factory([stuck], calls), attempts=30, pause=3, sleep=pauses.append)
    assert result['intentos'] == 1 and pauses == [] and result['fallidos'] == stuck['fallidos']


def test_items_seen_in_earlier_attempts_are_not_counted_twice():
    first = {'restaurados': ['a'], 'vigentes': [], 'obsoletos': ['old'], 'fallidos': [{'resource_uuid': 'b', 'codigo': 'UNCONFIRMED'}]}
    second = {'restaurados': ['b'], 'vigentes': ['a'], 'obsoletos': ['old'], 'fallidos': []}
    result = restore_boot.restore(runtime_factory([first, second], []), attempts=3, pause=0, sleep=lambda s: None)
    assert result['restaurados'] == ['a', 'b'] and result['vigentes'] == [] and result['obsoletos'] == ['old']


def test_gives_up_after_the_attempts_and_reports_the_failure_instead_of_hiding_it(capsys):
    stuck = {'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': [{'resource_uuid': 'a', 'codigo': 'UNCONFIRMED'}]}
    calls, pauses = [], []
    result = restore_boot.restore(runtime_factory([stuck], calls), attempts=3, pause=1, sleep=pauses.append)
    assert result['fallidos'] == stuck['fallidos'] and result['intentos'] == 3 and pauses == [1, 1] and len(calls) == 3


def test_main_exits_nonzero_and_says_so_when_something_was_not_restored(capsys, monkeypatch):
    stuck = {'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': [{'resource_uuid': 'a', 'codigo': 'IDENTITY_MISMATCH'}], 'intentos': 3}
    monkeypatch.setattr(restore_boot, 'restore', lambda: stuck)
    assert restore_boot.main() == 1
    assert '"estado": "con_fallos"' in capsys.readouterr().out


def test_success_exit_code_is_zero_even_when_there_is_nothing_to_restore(capsys, monkeypatch):
    monkeypatch.setattr(restore_boot, 'restore', lambda: {'restaurados': [], 'vigentes': [], 'obsoletos': [], 'fallidos': [], 'intentos': 1})
    assert restore_boot.main() == 0
    assert '"estado": "ok"' in capsys.readouterr().out
