"""Incremental secret masking and closed installer output, before persistence.

Raw bytes live only in bounded process memory. An installer is not a trusted log
producer: unknown lines are suppressed even if they contain no registered secret.
These classes never write files, stdout or journal.
"""
import base64
from collections import deque
import codecs
import json
import re
from urllib.parse import quote, quote_plus

from .protocol import JobError, PHASES, strict_json

MASK = '[REDACTED]'
SUPPRESSED = 'Salida omitida por seguridad.'
MAX_INPUT_BYTES = 65536


class TerminalCleaner:
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.state = 'normal'
        self.string_state = 'osc'

    def feed(self, raw, *, final=False):
        result = []
        for c in self.decoder.decode(raw, final=final):
            if self.state == 'escape':
                self.state = {'[': 'csi', ']': 'osc', 'P': 'string', '^': 'string', '_': 'string', 'X': 'string'}.get(c, 'normal')
            elif self.state == 'csi':
                if '@' <= c <= '~': self.state = 'normal'
            elif self.state in {'osc', 'string'}:
                if c == '\x1b': self.string_state, self.state = self.state, 'string_escape'
                elif c == '\x07' and self.state == 'osc': self.state = 'normal'
                elif c == '\x9c': self.state = 'normal'
            elif self.state == 'string_escape':
                self.state = 'normal' if c == '\\' else self.string_state
            elif c == '\x1b': self.state = 'escape'
            elif c == '\x9b': self.state = 'csi'
            elif c == '\x9d': self.state = 'osc'
            elif (ord(c) < 32 and c not in '\n\t' or 127 <= ord(c) <= 159
                    or '\u202a' <= c <= '\u202e' or '\u2066' <= c <= '\u2069' or c == '\ufeff'):
                continue
            else: result.append(c)
        return ''.join(result)


class SecretRedactor:
    def __init__(self, values):
        self._forms = set()
        self._values = 0
        self._started = self._closed = False
        self._cleaner = TerminalCleaner()
        self._pending = deque()
        self._state = 0
        for value in values: self.register(value)

    def register(self, value):
        if self._started or type(value) is not str or not value or self._values >= 20:
            raise JobError('INVALID_REQUEST')
        try:
            raw = value.encode('utf-8')
            if len(raw) > 4096: raise ValueError()
            forms = {value, json.dumps(value, ensure_ascii=True)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1],
                     quote(value, safe=''), quote_plus(value, safe='')}
            for encoding in (base64.b64encode, base64.urlsafe_b64encode):
                encoded = encoding(raw).decode('ascii'); forms.update({encoded, encoded.rstrip('=')})
            self._forms.update(TerminalCleaner().feed(f.encode(), final=True) for f in forms)
            self._forms.discard('')
            if sum(len(f.encode()) for f in self._forms) > 1048576: raise ValueError()
            self._values += 1
        except (ValueError, UnicodeError):
            raise JobError('INVALID_REQUEST') from None

    def _build(self):
        # Aho–Corasick: bounded pending prefix and linear streaming transitions.
        self._nodes = [{'next': {}, 'fail': 0, 'depth': 0, 'match': 0}]
        for form in sorted(self._forms):
            state = 0
            for char in form:
                node = self._nodes[state]
                if char not in node['next']:
                    node['next'][char] = len(self._nodes)
                    self._nodes.append({'next': {}, 'fail': 0, 'depth': node['depth']+1, 'match': 0})
                state = node['next'][char]
            self._nodes[state]['match'] = len(form)
        queue = deque(self._nodes[0]['next'].values())
        while queue:
            state = queue.popleft()
            for char, child in self._nodes[state]['next'].items():
                queue.append(child)
                fail = self._nodes[state]['fail']
                while fail and char not in self._nodes[fail]['next']: fail = self._nodes[fail]['fail']
                target = self._nodes[fail]['next'].get(char, 0)
                self._nodes[child]['fail'] = target
                self._nodes[child]['match'] = max(self._nodes[child]['match'], self._nodes[target]['match'])

    @property
    def pending_bytes(self):
        return sum(len(c.encode('utf-8')) for c in self._pending)

    def feed(self, raw, *, final=False):
        if self._closed or type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES: raise JobError('INVALID_REQUEST')
        if not self._started: self._build(); self._started = True
        result = []
        for char in self._cleaner.feed(raw, final=final):
            while self._state and char not in self._nodes[self._state]['next']:
                self._state = self._nodes[self._state]['fail']
            self._state = self._nodes[self._state]['next'].get(char, 0)
            self._pending.append(char)
            match = self._nodes[self._state]['match']
            if match:
                for _ in range(match): self._pending.pop()
                result.extend(self._pending); self._pending.clear()
                result.append(MASK); self._state = 0
            else:
                safe_count = len(self._pending) - self._nodes[self._state]['depth']
                for _ in range(safe_count): result.append(self._pending.popleft())
        if final:
            # A truncated credential is still private; never flush a known prefix.
            if self._pending: result.append(MASK)
            self._pending.clear(); self._closed = True
        return ''.join(result)


class ClosedOutput:
    """Only profile-approved structured events become displayable console text."""
    def __init__(self, values, *, packages=frozenset()):
        values = tuple(values)
        if (len(packages) > 2000 or any(type(p) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,99}', p) for p in packages)):
            raise JobError('INVALID_REQUEST')
        self._packages = frozenset(packages)
        self._streams = {s: {'redactor': SecretRedactor(values), 'line': [], 'bytes': 0,
                            'dropping': False, 'warned': False} for s in ('stdout', 'stderr')}

    @property
    def pending_bytes(self):
        return sum(v['bytes'] + v['redactor'].pending_bytes for v in self._streams.values())

    def _event(self, line):
        event = strict_json(line.encode(), limit=8192)
        if set(event) == {'event', 'phase'} and event['event'] == 'phase' and event['phase'] in PHASES:
            return {'preparacion': 'Preparando aplicación.', 'creacion': 'Creando recurso.',
                'entorno': 'Habilitando entorno.', 'instalacion': 'Instalando aplicación.',
                'configuracion': 'Configurando aplicación.', 'arranque': 'Iniciando aplicación.',
                'comprobacion': 'Comprobando acceso.', 'finalizada': 'Trabajo finalizado.'}[event['phase']]
        if (set(event) == {'event', 'name', 'status'} and event['event'] == 'package'
                and type(event['name']) is str and event['name'] in self._packages
                and event['status'] in {'installed', 'downloaded'}):
            verb = 'instalado' if event['status'] == 'installed' else 'descargado'
            return f"Paquete {verb}: {event['name']}."
        raise JobError('INVALID_REQUEST')

    def feed(self, stream, raw, *, final=False):
        if type(stream) is not str or stream not in self._streams: raise JobError('INVALID_REQUEST')
        state = self._streams[stream]; result = []
        text = state['redactor'].feed(raw, final=final)
        def suppress():
            if not state['warned']: result.append(SUPPRESSED); state['warned'] = True
        def line_end():
            if not state['dropping'] and state['line']:
                try:
                    result.append(self._event(''.join(state['line']))); state['warned'] = False
                except (JobError, TypeError, ValueError): suppress()
            state['line'].clear(); state['bytes'] = 0; state['dropping'] = False
        for char in text:
            if char == '\n': line_end()
            elif not state['dropping']:
                state['bytes'] += len(char.encode('utf-8'))
                if state['bytes'] > 8192:
                    state['line'].clear(); state['bytes'] = 0; state['dropping'] = True; suppress()
                else: state['line'].append(char)
        if final: line_end()
        return result
