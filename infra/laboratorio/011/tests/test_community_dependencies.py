import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
s = importlib.util.spec_from_file_location('community_dependency011', ROOT / 'spike_community.py')
community = importlib.util.module_from_spec(s); s.loader.exec_module(community)


@pytest.fixture
def lock():
    return json.loads((ROOT / 'community-dependencies.lock.json').read_text())


def test_frozen_signed_repository_coordinates_and_caddy_artifact_are_accepted(lock):
    assert community.validate_dependencies(lock) == lock


@pytest.mark.parametrize('url', ['http://snapshot.debian.org/archive/debian/',
    'https://snapshot.debian.org@127.0.0.1/archive/debian/', 'https://deb.debian.org/debian/',
    'https://snapshot.debian.org/archive/debian/now/dists/trixie/InRelease'])
def test_changed_or_mutable_apt_source_is_rejected(lock, url):
    lock['apt']['releases'][0]['url'] = url
    with pytest.raises(ValueError, match='DEPENDENCY_REPOSITORY'): community.validate_dependencies(lock)


def test_all_three_release_manifests_are_required(lock):
    lock['apt']['releases'].pop()
    with pytest.raises(ValueError, match='DEPENDENCY_REPOSITORY'): community.validate_dependencies(lock)


@pytest.mark.parametrize('field,value', [('version', 'latest'), ('sha256', '0' * 8),
    ('url', 'https://localhost:8001/image.deb'), ('bytes', 100 * 1024**2)])
def test_unfrozen_or_unapproved_release_is_rejected(lock, field, value):
    lock['caddy'][field] = value
    with pytest.raises(ValueError, match='DEPENDENCY_ARTIFACT'): community.validate_dependencies(lock)


def test_apt_timestamp_cannot_change_without_freezing_corresponding_url(lock):
    lock['apt']['releases'][0]['timestamp'] = '20260101T000000Z'
    with pytest.raises(ValueError, match='DEPENDENCY_REPOSITORY'): community.validate_dependencies(lock)
