"""Bash real, sólo definiciones de política y fixtures locales; sin instaladores."""

from pathlib import Path
import subprocess

import pytest


POLICY = Path(__file__).parents[1] / 'community_bootstrap_policy.func'


def shell(tmp_path, program):
    core = tmp_path / 'core'; (core / 'lib').mkdir(parents=True)
    (core / 'lib/db.func').write_text('NAP_LOCAL_HELPER=loaded\n')
    env = {'PATH': '/usr/bin:/bin', 'NAP_CORE_DIR': str(core)}
    return subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c',
                           'source "$1" || exit 97; ' + program, 'nap-policy-test', str(POLICY)],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)


@pytest.mark.integration
def test_messages_and_command_output_are_never_raw_logs(tmp_path):
    result = shell(tmp_path, 'msg_info do-not-copy-secret; log_msg do-not-copy-secret; '
                   'set_std_mode; $STD printf do-not-copy-secret; printf safe-result')
    assert result.returncode == 0 and result.stdout == 'safe-result' and result.stderr == ''
    assert not list(tmp_path.rglob('*.log'))


@pytest.mark.integration
def test_unknown_helpers_and_host_wrappers_cannot_be_sourced(tmp_path):
    result = shell(tmp_path, '_cs_source_func core/build.func; printf forbidden')
    assert result.returncode == 84 and 'forbidden' not in result.stdout


@pytest.mark.integration
def test_approved_helper_is_local_and_prompt_cannot_be_ignored(tmp_path):
    result = shell(tmp_path, '_cs_source_func lib/db.func; printf "$NAP_LOCAL_HELPER"; '
                   'read -r -p do-not-copy-secret reply || true; printf forbidden')
    assert result.returncode == 90 and result.stdout == 'loaded' and result.stderr == ''


@pytest.mark.integration
def test_internal_noninteractive_read_still_works(tmp_path):
    result = shell(tmp_path, 'read -r value <<<"local-value"; printf "$value"')
    assert result.returncode == 0 and result.stdout == 'local-value' and result.stderr == ''


@pytest.mark.integration
def test_undeclared_network_download_cannot_be_ignored(tmp_path):
    result = shell(tmp_path, 'curl https://example.invalid/unlisted || true; printf forbidden')
    assert result.returncode == 85 and result.stdout == '' and result.stderr == ''
