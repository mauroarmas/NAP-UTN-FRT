#!/bin/bash
set -euo pipefail

# APT ya instaló todas las versiones exactas del lock. El código y lock de
# Composer se verifican antes de instalar dependencias del producto fijado.
test -x /usr/bin/php8.3
test -x /usr/sbin/php-fpm8.3
test -x /usr/bin/mariadb
test -x /usr/sbin/nginx
test -x /usr/bin/composer
test -x /usr/bin/curl
/usr/bin/python3 - <<'PY'
import json, re, subprocess, sys
sys.path.insert(0, '/opt/nap-build')
from bootstrap import install_application
from common import configure_console
with open('/opt/nap-build/plan.json') as source:
    plan = json.load(source)
components = plan['manifest']['runtime']['components']
php = subprocess.check_output(['/usr/bin/php8.3', '-r', 'echo PHP_VERSION;'], text=True)
maria = subprocess.check_output(['/usr/bin/mariadb', '--version'], text=True)
match = re.search(r'(?:Distrib |from )(10\.11\.[0-9]+)', maria)
if php != components['php']['version'] or not match or match.group(1) != components['mariadb']['version']:
    raise SystemExit('Versiones de runtime diferentes del manifiesto')
install_application(plan)
configure_console()
PY
COMPOSER_HOME=/tmp/nap-composer COMPOSER_ALLOW_SUPERUSER=1 /usr/bin/composer install --working-dir=/var/www/bookstack \
    --no-dev --prefer-dist --no-interaction --no-plugins --no-scripts --optimize-autoloader
COMPOSER_HOME=/tmp/nap-composer COMPOSER_ALLOW_SUPERUSER=1 /usr/bin/composer check-platform-reqs --working-dir=/var/www/bookstack --no-dev
rm -f /etc/nginx/sites-enabled/default /etc/php/8.3/fpm/pool.d/www.conf
/usr/bin/systemctl mask mariadb.service nginx.service php8.3-fpm.service
# Sin .env, APP_KEY, usuarios ni bases de aplicación; el saneador limpia también
# bases inicializadas por los paquetes y caches/sesiones antes de crear la imagen.
