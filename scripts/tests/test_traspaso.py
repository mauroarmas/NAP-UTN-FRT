"""Guardas del traspaso: sin Docker ni acceso a datos del laboratorio."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('traspaso', Path(__file__).parents[1] / 'traspaso.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / '.env.example').write_text((transfer.ROOT / '.env.example').read_text())
        self.root_patch = patch.object(transfer, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_init_generates_distinct_private_keys_and_never_overwrites(self):
        transfer.init_env()
        path = self.root / '.env'
        original = path.read_bytes()
        self.assertFalse(path.stat().st_mode & 0o077)
        self.assertNotIn(b'GENERAR_', original)
        lines = dict(v.split('=', 1) for v in original.decode().splitlines() if v and not v.startswith('#'))
        self.assertNotEqual(lines['SECRET_KEY'], lines['CSRF_SECRET'])
        ring = json.loads(lines['SECRET_KEYRING'].strip("'"))
        self.assertEqual(len(base64.urlsafe_b64decode(ring['local-v1'])), 32)
        with self.assertRaises(FileExistsError):transfer.init_env()
        self.assertEqual(path.read_bytes(), original)

    def test_import_preserves_existing_data_key(self):
        value = {'secret_keyring': {'old-v1': base64.urlsafe_b64encode(b'x' * 32).decode()}, 'secret_active_key': 'old-v1'}
        keyring = self.root / 'keyring.json';keyring.write_text(json.dumps(value));keyring.chmod(0o600)
        transfer.init_env(keyring)
        env = (self.root / '.env').read_text()
        self.assertIn('SECRET_ACTIVE_KEY=old-v1', env)
        self.assertIn(value['secret_keyring']['old-v1'], env)

    def test_shared_or_linked_keyring_is_rejected(self):
        keyring = self.root / 'keyring.json';keyring.write_text('{}');keyring.chmod(0o644)
        with self.assertRaises(ValueError):transfer.read_keyring(keyring)
        link = self.root / 'linked.json';link.symlink_to(keyring)
        with self.assertRaises(OSError):transfer.read_keyring(link)

    def test_invalid_key_identifier_cannot_inject_env_line(self):
        value = {'secret_keyring': {'bad\nCOMPOSE_FILE=other': base64.urlsafe_b64encode(b'x' * 32).decode()},
                 'secret_active_key': 'bad\nCOMPOSE_FILE=other'}
        with self.assertRaises(ValueError):transfer.validate_keyring(value)

    def test_export_inside_repository_is_rejected_before_docker(self):
        with patch.object(transfer, 'run') as docker:
            with self.assertRaises(ValueError):transfer.export(self.root / 'private', 'db', 'api')
            docker.assert_not_called()

    def test_wrong_restore_project_is_rejected_before_sql(self):
        result = type('Result', (), {'stdout': json.dumps([{'Config': {'Labels': {
            'com.docker.compose.project': 'operational', 'com.docker.compose.service': 'db'}}}]).encode()})()
        with patch.object(transfer, 'run', return_value=result), patch.object(transfer, 'sql') as sql:
            with self.assertRaises(ValueError):transfer.restore(self.root, 'operational-db')
            sql.assert_not_called()

    def test_modified_dump_is_rejected_before_restoration(self):
        (self.root / 'portal.dump').write_bytes(b'changed')
        (self.root / 'keyring.json').write_bytes(b'{}')
        (self.root / 'manifest.json').write_text(json.dumps({'format': 1, 'sha256': {
            'portal.dump': '0' * 64, 'keyring.json': '0' * 64}}))
        with patch.object(transfer, 'restored_inventory') as restore:
            with self.assertRaises(ValueError):transfer.verify(self.root)
            restore.assert_not_called()


if __name__ == '__main__':
    unittest.main()
