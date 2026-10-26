"""Aplicación académica de ensayo: un dato persistente, sin dependencias externas."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3


PAGE = '''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus · Aplicación de prueba</title>
<style>body{font:17px system-ui;background:#f1f5f9;color:#172033;margin:0;padding:5vw}
main{max-width:640px;margin:3vh auto;background:white;border-radius:20px;padding:32px;
box-shadow:0 12px 40px #17203312}small{color:#4559c7}h1{font-size:28px}
textarea{box-sizing:border-box;width:100%;min-height:140px;border:1px solid #cbd5e1;
border-radius:10px;padding:12px;font:inherit;margin:10px 0}button{background:#4559c7;
color:white;border:0;border-radius:9px;padding:12px 22px;font:inherit;cursor:pointer}
[role=status]{min-height:24px;color:#166534}</style>
<main><small>APLICACIÓN DE CÁTEDRA · DEMOSTRACIÓN</small><h1>Tu espacio de prueba</h1>
<p>Guardá una nota. Seguirá acá después de reiniciar esta instancia.</p>
<form id="form"><label for="note">Nota</label><textarea id="note" maxlength="2000"></textarea>
<button id="save">Guardar nota</button></form><p role="status" id="status">Cargando…</p></main>
<script>
const note=document.getElementById('note'),status=document.getElementById('status');
fetch('./api/note').then(r=>{if(!r.ok)throw Error();return r.json()}).then(v=>{
note.value=v.note;status.textContent='Lista para usar.'}).catch(()=>status.textContent='No se pudo cargar.');
document.getElementById('form').addEventListener('submit',async e=>{e.preventDefault();
const button=document.getElementById('save');button.disabled=true;status.textContent='Guardando…';
try{const r=await fetch('./api/note',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({note:note.value})});if(!r.ok)throw Error();status.textContent='Nota guardada.'}
catch{status.textContent='No se pudo guardar. Intentá nuevamente.'}finally{button.disabled=false}});
</script></html>'''.encode()


class NoteStore:
    def __init__(self, directory):
        root = Path(directory)
        if not root.is_absolute():
            raise ValueError('El directorio de datos debe ser absoluto')
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'notes.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS note (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=3)

    def read(self):
        with self.connect() as db:
            row = db.execute('SELECT value FROM note WHERE id=1').fetchone()
        return row[0] if row else ''

    def write(self, note):
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError('Nota inválida')
        with self.connect() as db:
            db.execute('INSERT INTO note VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (note,))


def dispatch(method, path, body, store):
    if method == 'GET' and path == '/':
        return 200, 'text/html; charset=utf-8', PAGE
    if method == 'GET' and path == '/health':
        store.read()
        value = {'status': 'ok'}
    elif method == 'GET' and path == '/api/note':
        value = {'note': store.read()}
    elif method == 'POST' and path == '/api/note':
        try:
            value = json.loads(body)
            if not isinstance(value, dict) or set(value) != {'note'}:
                raise ValueError()
            store.write(value['note'])
            value = {'saved': True}
        except (ValueError, UnicodeError):
            return 422, 'application/json', b'{"error":"Nota invalida"}'
    else:
        return 404, 'application/json', b'{"error":"No encontrado"}'
    return 200, 'application/json', json.dumps(value, ensure_ascii=False).encode()


class Handler(BaseHTTPRequestHandler):
    def _serve(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 <= length <= 8192:
                self.send_error(413)
                return
            if self.command == 'POST' and self.headers.get_content_type() != 'application/json':
                self.send_error(415)
                return
            status, content_type, body = dispatch(self.command, self.path,
                                                self.rfile.read(length), self.server.store)
        except (sqlite3.Error, OSError, ValueError):
            status, content_type, body = 503, 'application/json', b'{"error":"No disponible"}'
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    do_GET = _serve
    do_POST = _serve

    def log_message(self, *_):
        pass  # No registrar cuerpos, cookies, cabeceras ni rutas del cliente.

    def setup(self):
        self.request.settimeout(10)
        super().setup()


def main():
    server = ThreadingHTTPServer(('0.0.0.0', 8080), Handler)
    server.store = NoteStore(os.environ.get('NAP_DEMO_DATA', '/data'))
    server.serve_forever()


if __name__ == '__main__':
    main()
