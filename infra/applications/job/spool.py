"""Bounded, sanitized console spool. SQLite commits are the publication boundary.

Only committed fragments receive externally visible source sequences. Failed
writes never reuse a published sequence. A recovered writer reports unconfirmed
write attempts separately; it cannot invent a durable count after a disk failure
and process crash. Quota eviction records exact original ranges/byte counts.
"""
from datetime import datetime, timezone
import math
import os
import sqlite3

from .protocol import JobError, PHASES, canonical, MAX_FRAGMENT_BYTES, MAX_READ_BYTES, _timestamp
from .state import uuid_text

APPLICATION_ID = 0x4E415031
META_INTS = ('last_seq', 'ack_seq', 'retained_bytes', 'rows_count', 'dropped_bytes', 'dropped_messages',
             'lost_from', 'lost_through', 'lost_bytes', 'max_bytes', 'max_records')


class Spool:
    def __init__(self, *, store, execution_id, max_bytes=2000000, max_records=4096,
                 now=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')):
        if (type(max_bytes) is not int or not 1 <= max_bytes <= 10000000
                or type(max_records) is not int or not 1 <= max_records <= 4096): raise JobError('INVALID_REQUEST')
        self.store, self.execution_id = store, uuid_text(execution_id)
        self.max_bytes, self.max_records, self.now = max_bytes, max_records, now
        self._unconfirmed = 0

    @property
    def name(self): return 'spool.' + self.execution_id + '.sqlite3'

    def _header(self, connection, job):
        values = connection.execute('SELECT * FROM meta WHERE id=1').fetchone()
        if values is None or connection.execute('SELECT count(*) FROM meta').fetchone()[0] != 1: raise JobError('UNCONFIRMED')
        meta = dict(values)
        if set(meta) != {'id', 'execution_id', 'fingerprint', *META_INTS}: raise JobError('UNCONFIRMED')
        if (meta['execution_id'] != self.execution_id or meta['fingerprint'] != job['fingerprint']
                or any(type(meta[k]) is not int or meta[k] < 0 for k in META_INTS)
                or meta['ack_seq'] > meta['last_seq'] or job['last_source_seq'] > meta['last_seq']
                or job['acknowledged_seq'] > meta['ack_seq']
                or not 1 <= meta['max_bytes'] <= 10000000 or not 1 <= meta['max_records'] <= 4096
                or meta['retained_bytes'] > meta['max_bytes'] or meta['rows_count'] > meta['max_records']
                or not (meta['lost_from'] == meta['lost_through'] == meta['lost_bytes'] == 0
                    or 1 <= meta['lost_from'] <= meta['lost_through'] <= meta['last_seq'])):
            raise JobError('UNCONFIRMED')
        return meta

    def _connect(self, job, *, create=False):
        self.store._open()
        connection = None
        try:
            flags = os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
            try: descriptor = os.open(self.name, flags, 0o600, dir_fd=self.store.fd)
            except FileNotFoundError:
                if job['last_source_seq'] or job['acknowledged_seq']: raise JobError('UNCONFIRMED')
                return None
            try: self.store._private_file(os.fstat(descriptor))
            finally: os.close(descriptor)
            # The directory fd anchors recovery/journal paths too. No client path.
            connection = sqlite3.connect(f'file:/proc/self/fd/{self.store.fd}/{self.name}?mode=rw',
                uri=True, timeout=0.05, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA temp_store=MEMORY')
            connection.execute('PRAGMA secure_delete=ON')
            application = connection.execute('PRAGMA application_id').fetchone()[0]
            tables = {(r[0], r[1]) for r in connection.execute("SELECT name,type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'")}
            if application == 0 and not tables:
                if job['last_source_seq'] or job['acknowledged_seq']: raise JobError('UNCONFIRMED')
                if not create: connection.close(); return None
                connection.execute('PRAGMA page_size=4096')
                connection.execute('PRAGMA auto_vacuum=INCREMENTAL')
                connection.execute('PRAGMA journal_mode=DELETE')
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('''CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1),
                    execution_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    last_seq INTEGER NOT NULL DEFAULT 0, ack_seq INTEGER NOT NULL DEFAULT 0,
                    retained_bytes INTEGER NOT NULL DEFAULT 0, rows_count INTEGER NOT NULL DEFAULT 0,
                    dropped_bytes INTEGER NOT NULL DEFAULT 0, dropped_messages INTEGER NOT NULL DEFAULT 0,
                    lost_from INTEGER NOT NULL DEFAULT 0, lost_through INTEGER NOT NULL DEFAULT 0,
                    lost_bytes INTEGER NOT NULL DEFAULT 0, max_bytes INTEGER NOT NULL, max_records INTEGER NOT NULL)''')
                connection.execute('''CREATE TABLE frames (seq INTEGER PRIMARY KEY, captured_at TEXT NOT NULL,
                    fase TEXT NOT NULL, stream TEXT NOT NULL, texto_depurado TEXT NOT NULL, utf8_bytes INTEGER NOT NULL)''')
                connection.execute('INSERT INTO meta(id,execution_id,fingerprint,max_bytes,max_records) VALUES (1,?,?,?,?)',
                    (self.execution_id, job['fingerprint'], self.max_bytes, self.max_records))
                connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                connection.execute('PRAGMA user_version=1'); connection.commit()
            elif (application != APPLICATION_ID or tables != {('meta', 'table'), ('frames', 'table')}
                    or connection.execute('PRAGMA user_version').fetchone()[0] != 1): raise JobError('UNCONFIRMED')
            if {r['name'] for r in connection.execute('PRAGMA table_info(frames)')} != {'seq','captured_at','fase','stream','texto_depurado','utf8_bytes'}:
                raise JobError('UNCONFIRMED')
            meta = self._header(connection, job)
            if create:
                connection.execute('PRAGMA synchronous=FULL')
                pages = max(256, math.ceil(meta['max_bytes']/4096)*2 + 64)
                if connection.execute(f'PRAGMA max_page_count={pages}').fetchone()[0] > pages: raise JobError('NO_SPACE')
            return connection
        except Exception:
            if connection is not None: connection.close()
            raise

    @staticmethod
    def _safe(fase, stream, text):
        if type(fase) is not str or fase not in PHASES or type(stream) is not str or stream not in {'sistema', 'stdout', 'stderr'}: raise JobError('INVALID_REQUEST')
        if (type(text) is not str or not 1 <= len(text.encode('utf-8')) <= MAX_FRAGMENT_BYTES
                or any(ord(c) < 32 and c not in '\n\t' or 127 <= ord(c) <= 159
                    or '\u202a' <= c <= '\u202e' or '\u2066' <= c <= '\u2069' for c in text)):
            raise JobError('INVALID_REQUEST')

    def _append(self, connection, meta, *, fase, stream, text, captured_at):
        size = len(text.encode('utf-8')); sequence = meta['last_seq'] + 1
        if sequence > 2**63-1: raise JobError('NO_SPACE')
        removed = []
        if meta['retained_bytes'] + size > meta['max_bytes'] or meta['rows_count'] + 1 > meta['max_records']:
            for row in connection.execute('SELECT seq,utf8_bytes FROM frames ORDER BY seq').fetchall():
                removed.append(row); meta['retained_bytes'] -= row['utf8_bytes']; meta['rows_count'] -= 1
                if meta['retained_bytes'] + size <= meta['max_bytes'] and meta['rows_count'] + 1 <= meta['max_records']: break
        if removed:
            connection.execute('DELETE FROM frames WHERE seq<=?', (removed[-1]['seq'],))
            meta['lost_from'] = meta['lost_from'] or removed[0]['seq']
            meta['lost_through'] = removed[-1]['seq']
            lost = sum(r['utf8_bytes'] for r in removed)
            meta['lost_bytes'] += lost; meta['dropped_bytes'] += lost; meta['dropped_messages'] += len(removed)
        if size > meta['max_bytes']:
            meta['lost_from'] = meta['lost_from'] or sequence
            meta['lost_through'] = sequence; meta['lost_bytes'] += size
            meta['dropped_bytes'] += size; meta['dropped_messages'] += 1
        else:
            connection.execute('INSERT INTO frames VALUES (?,?,?,?,?,?)', (sequence, captured_at, fase, stream, text, size))
            meta['retained_bytes'] += size; meta['rows_count'] += 1
        meta['last_seq'] = sequence

    @staticmethod
    def _save(connection, meta):
        columns = ('last_seq', 'ack_seq', 'retained_bytes', 'rows_count', 'dropped_bytes', 'dropped_messages',
                   'lost_from', 'lost_through', 'lost_bytes')
        connection.execute('UPDATE meta SET ' + ','.join(k+'=?' for k in columns) + ' WHERE id=1', tuple(meta[k] for k in columns))

    def append_safe(self, *, fase, stream, texto_depurado):
        """Caller supplies only output from the closed redactor/event producer."""
        self._safe(fase, stream, texto_depurado)
        captured = self.now(); _timestamp(captured)
        connection = None
        try:
            job = self.store.read_job(self.execution_id)
            if job is None: raise JobError('UNCONFIRMED')
            with self.store.lock('resource', job['identity']['resource_uuid']):
                job = self.store.read_job(self.execution_id)
                if job['worker_finished']: return False  # No source cursor can grow after a worker result.
                connection = self._connect(job, create=True)
                connection.execute('BEGIN IMMEDIATE'); meta = self._header(connection, job)
                if self._unconfirmed:
                    self._append(connection, meta, fase=fase, stream='sistema', captured_at=captured,
                        text=f'No se pudo confirmar el registro de {self._unconfirmed} mensajes anteriores de consola.')
                self._append(connection, meta, fase=fase, stream=stream, text=texto_depurado, captured_at=captured)
                self._save(connection, meta); connection.commit()
                self._unconfirmed = 0
                return True
        except (sqlite3.Error, OSError, JobError):
            if connection is not None:
                try: connection.rollback()
                except sqlite3.Error: pass
            self._unconfirmed = min(self._unconfirmed+1, 2**63-1)
            return False
        finally:
            if connection is not None: connection.close()

    def summary_locked(self, job):
        connection = None
        try:
            connection = self._connect(job)
            if connection is None: return {'last_source_seq': 0, 'acknowledged_seq': 0}
            meta = self._header(connection, job)
            return {'last_source_seq': meta['last_seq'], 'acknowledged_seq': meta['ack_seq']}
        except (sqlite3.Error, OSError): raise JobError('UNCONFIRMED') from None
        finally:
            if connection is not None: connection.close()

    def read_locked(self, job, *, after, limit_bytes):
        if type(after) is not int or not 0 <= after <= 2**63-1 or type(limit_bytes) is not int or not 1 <= limit_bytes <= MAX_READ_BYTES:
            raise JobError('INVALID_REQUEST')
        connection = None
        try:
            connection = self._connect(job)
            if connection is None: return {'items': [], 'dropped_ranges': []}
            meta = self._header(connection, job); items = []
            for row in connection.execute('SELECT * FROM frames WHERE seq>? ORDER BY seq LIMIT 1000', (max(after, meta['ack_seq']),)):
                item = {'execution_id': self.execution_id, 'source_seq': row['seq'], 'captured_at': row['captured_at'],
                        'fase': row['fase'], 'stream': row['stream'], 'texto_depurado': row['texto_depurado']}
                if len(canonical([*items, item])) > limit_bytes: break
                items.append(item)
            ranges = []
            if meta['lost_through'] > max(after, meta['ack_seq']):
                ranges.append({'from_seq': meta['lost_from'], 'through_seq': meta['lost_through'], 'bytes': meta['lost_bytes']})
            return {'items': items, 'dropped_ranges': ranges}
        except (sqlite3.Error, OSError): raise JobError('UNCONFIRMED') from None
        finally:
            if connection is not None: connection.close()

    def ack_locked(self, job, *, through_seq):
        connection = None
        try:
            if type(through_seq) is not int or through_seq < 0: raise JobError('INVALID_REQUEST')
            connection = self._connect(job)
            if connection is None:
                if through_seq != 0: raise JobError('INVALID_REQUEST')
                return
            connection.execute('BEGIN IMMEDIATE'); meta = self._header(connection, job)
            if through_seq > meta['last_seq']: raise JobError('INVALID_REQUEST')
            if through_seq > meta['ack_seq']:
                rows = connection.execute('SELECT utf8_bytes FROM frames WHERE seq<=?', (through_seq,)).fetchall()
                connection.execute('DELETE FROM frames WHERE seq<=?', (through_seq,))
                meta['retained_bytes'] -= sum(r[0] for r in rows); meta['rows_count'] -= len(rows)
                meta['ack_seq'] = through_seq
                if through_seq >= meta['lost_through']: meta.update(lost_from=0, lost_through=0, lost_bytes=0)
                self._save(connection, meta)
            connection.commit()
            try: connection.execute('PRAGMA incremental_vacuum').fetchall()
            except sqlite3.Error: pass  # ACK is already durable; text is securely erased.
        except (sqlite3.Error, OSError): raise JobError('UNCONFIRMED') from None
        finally:
            if connection is not None:
                if connection.in_transaction: connection.rollback()
                connection.close()
