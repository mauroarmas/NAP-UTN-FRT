"""Ensayo explícito dentro del contenedor descartable; nunca en el host/PVE.

Montar checkout de solo lectura en /source, ejecutar con --network none.
Los comandos PVE y systemctl son dobles; sshd, sudo y el usuario son reales.
"""
import base64, importlib.util, json, os, pathlib, shutil, subprocess
if (os.environ.get('NAP_SETUP_SANDBOX') != '1' or not pathlib.Path('/.dockerenv').is_file()
        or pathlib.Path('/etc/pve').exists()):
    raise SystemExit('Solo ejecutar en el contenedor descartable vacío con NAP_SETUP_SANDBOX=1')
# El bootstrap remoto establece esta umask; comprobar permisos efectivos, no
# solamente los bits solicitados a mkdir.
os.umask(0o077)
root = pathlib.Path('/root/nap009-prep')
for rel in ['infra/runner/configure_access.py', 'infra/runner/nap_guest_runner.py', 'infra/runner/node_executor.py', 'infra/runner/nap-guest-runner', 'backend/app/schemas/guest_runner.py', 'backend/app/utils/artifact_registry.py']:
 target=root/rel
 target.parent.mkdir(parents=True, exist_ok=True)
 shutil.copyfile('/source/'+rel, target)
 target.chmod(0o644)
pathlib.Path('/etc/pve/nodes/proxmox').mkdir(parents=True)
pathlib.Path('/etc/pve/local').symlink_to('nodes/proxmox', target_is_directory=True)
pathlib.Path('/run/sshd').mkdir(exist_ok=True)
for path in ['/usr/sbin/pct', '/usr/bin/pvesh']:
 pathlib.Path(path).write_text('#!/bin/sh\necho unexpected-PVE-call >&2\nexit 99\n')
 pathlib.Path(path).chmod(0o755)
pathlib.Path('/usr/bin/systemctl').write_text('#!/bin/sh\ntest "$1 $2" = "reload ssh" || exit 99\nprintf reload >> /tmp/reloaded\n')
pathlib.Path('/usr/bin/systemctl').chmod(0o755)
subprocess.run(['/usr/bin/ssh-keygen', '-A'],check=True,stdout=subprocess.DEVNULL)
spec=importlib.util.spec_from_file_location('setup', root/'infra/runner/configure_access.py')
setup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
blob=b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'+bytes(range(32))
key='ssh-ed25519 '+base64.b64encode(blob).decode()
# Una instalación ajena puede haber elegido un directorio privado: no ampliar
# su acceso ni crear cuenta/estado antes de informar ese conflicto.
pathlib.Path('/etc/nap').mkdir(mode=0o700)
try:
 setup.apply(root,setup.access_files('172.16.36.1',key),'172.16.36.1','172.16.36.100')
except ValueError as exc:
 assert 'preexistente' in str(exc)
 assert not pathlib.Path('/var/lib/nap-runner').exists()
else:
 raise AssertionError('Se amplió un directorio privado existente')
pathlib.Path('/etc/nap').chmod(0o755)
files=setup.access_files('172.16.36.1', key)
receipt=setup.apply(root,files,'172.16.36.1','172.16.36.100')
for directory in ['/etc/nap', '/etc/nap/runner', '/var/lib/nap-runner-login']:
 assert pathlib.Path(directory).stat().st_mode & 0o777 == 0o755, directory
assert pathlib.Path('/tmp/reloaded').read_text() == 'reload'
assert len(receipt) == 9
assert pathlib.Path('/etc/nap/runner/registry.json').read_text().strip() == '{}'
assert (pathlib.Path('/var/lib/nap-runner/hmac.key').stat().st_mode & 0o777) == 0o600
# El usuario no puede ejecutar un shell, pct ni argumentos en el wrapper.
for argv in [['/bin/sh', '-c', 'id'], ['/usr/sbin/pct', 'list'], ['/usr/local/sbin/nap-guest-runner', 'extra']]:
 result=subprocess.run(['/usr/sbin/runuser','-u','naprunner','--','/usr/bin/sudo','-n',*argv],capture_output=True)
 assert result.returncode != 0, argv
# No asumir que una segunda ejecución autoriza reusar la cuenta.
try:
 setup.apply(root,setup.access_files('172.16.36.1',key),'172.16.36.1','172.16.36.100')
except ValueError as exc:
 assert 'ya existe' in str(exc)
else:
 raise AssertionError('Cuenta existente aceptada')
print(json.dumps({'entorno':'contenedor Debian descartable, sin red/PVE', 'instalacion': 'correcta', 'sudo_shell_pct_argumentos': 'denegados', 'segunda_instalacion': 'rechazada'}))

import socket, time
# Claves efímeras solo del ensayo, sin red fuera del contenedor.
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f','/root/client-key'],check=True)
key=pathlib.Path('/root/client-key.pub').read_text().split()
auth=pathlib.Path('/etc/nap/runner/authorized_keys')
auth.write_text('restrict,from="172.16.36.1/32" '+key[0]+' '+key[1]+'\n')
serverkey=pathlib.Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
known=pathlib.Path('/root/known-hosts')
known.write_text('[127.0.0.1]:2222 '+serverkey[0]+' '+serverkey[1]+'\n')
server=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-p','2222'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for attempt in range(30):
  try:
   with socket.create_connection(('127.0.0.1',2222),timeout=.1): pass
   break
  except OSError: time.sleep(.05)
 base=['/usr/bin/ssh','-F','/dev/null','-T','-p','2222','-i','/root/client-key','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/root/known-hosts','-o','GlobalKnownHostsFile=/dev/null','-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-l','naprunner']
 denied=subprocess.run([*base,'127.0.0.1','id'],input=b'{}',capture_output=True,timeout=5)
 assert denied.returncode != 0 and b'Permission denied' in denied.stderr, denied.stderr
 # Solo el fixture se adapta a loopback: conservar ForceCommand y demás opciones.
 auth.write_text(auth.read_text().replace('172.16.36.1/32','127.0.0.1/32'))
 forced=subprocess.run([*base,'127.0.0.1','/bin/sh -c id'],input=b'{}',capture_output=True,timeout=5)
 assert forced.returncode == 0, forced.stderr
 assert json.loads(forced.stdout)['error']['code'] == 'INVALID_REQUEST'
 forward=subprocess.run([*base,'-N','-R','127.0.0.1:23456:127.0.0.1:2222','-o','ExitOnForwardFailure=yes','127.0.0.1'],capture_output=True,timeout=5)
 assert forward.returncode != 0 and b'forwarding failed' in forward.stderr, forward.stderr
 print(json.dumps({'ssh_local':'correcto', 'otro_origen':'denegado', 'comando_shell':'sustituido_por_wrapper', 'forwarding':'denegado', 'PAM_password_bloqueado':'autenticacion_publickey_correcta'}))
finally:
 server.terminate();server.wait(timeout=3)

