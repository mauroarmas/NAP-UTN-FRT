"""Linux LXC con cuenta guest propia y login autenticado de consola."""
import re

if __package__:
    from infra.services.common import GuestError, GuestSystem, main, configure_console, CONSOLE_UNITS, CONSOLE_LOGIN
else:
    from common import GuestError, GuestSystem, main, configure_console, CONSOLE_UNITS, CONSOLE_LOGIN


UNITS, LOGIN = CONSOLE_UNITS, CONSOLE_LOGIN
SUDO = 'napadmin ALL=(ALL:ALL) ALL\n'


def configure_image(system=None):
    configure_console(system)


class Linux:
    parameters = ['display_name']
    secret_fields = ['guest_password']

    def prepare(self, context):
        system = context.system
        if not context.steps.get('create_user') and system.account('napadmin'):
            raise GuestError('UNSUPPORTED_GUEST')
        context.step('console_configuration', lambda: configure_image(system))
        def create_user():
            if not system.account('napadmin'):
                system.run(['/usr/sbin/useradd', '--create-home', '--shell', '/bin/bash', 'napadmin'])
        context.step('create_user', create_user)
        password = context.request['secrets']['guest_password']
        def set_password():
            current = system.shadow('napadmin')
            if current is None:
                raise GuestError('UNCONFIRMED')
            if current.startswith(('!', '*')):
                system.run(['/usr/sbin/chpasswd'], input='napadmin:' + password + '\n')
            elif not system.password_matches('napadmin', password):
                # Un efecto desconocido no autoriza restablecer una contraseña
                # que cambió desde el intento anterior.
                raise GuestError('UNCONFIRMED')
        context.step('initial_password', set_password)
        context.step('sudo_configuration', lambda: system.write('etc/sudoers.d/napadmin', SUDO, mode=0o440))
        system.run(['/usr/sbin/visudo', '--check', '--file', '/etc/sudoers.d/napadmin'])
        system.run(['/usr/bin/systemctl', 'daemon-reload'])

    def inspect(self, context):
        system = context.system
        account = system.account('napadmin')
        root_password = system.shadow('root') or ''
        configured = all(system.read('etc/systemd/system/' + unit + '.d/zz-nap-login.conf') == LOGIN for unit in UNITS)
        ready = bool(account and account['uid'] >= 1000 and account['shell'] == '/bin/bash'
            and root_password.startswith(('!', '*')) and system.read('etc/sudoers.d/napadmin') == SUDO and configured)
        return {'ready': ready, 'bootstrap_completed': bool(context.state.get('completed')),
            'username': 'napadmin', 'checks': ['linux-ready-v1'] if ready else []}

    def verify(self, context):
        result = self.inspect(context)
        if not result['ready']:
            raise GuestError('PROBE_FAILED')
        context.system.run(['/usr/sbin/visudo', '--check', '--file', '/etc/sudoers.d/napadmin'])
        effective = context.system.run(['/usr/bin/systemctl', 'show', '--property=ExecStart', '--value', *UNITS])
        active = '\n'.join(line for line in effective.splitlines() if not line.lstrip().startswith('#'))
        # Antes de entregar también se comprueba un login real desde consola;
        # esta prueba local solo acredita configuración sin autologin.
        if 'agetty' not in active or '--autologin' in active or re.search(r'\s-a(?:\s|=)', active):
            raise GuestError('PROBE_FAILED')
        return result


if __name__ == '__main__':
    main(Linux())
