#!/usr/bin/env bash
# Modos técnicos del gate Community; no publica aplicaciones ni habilita perfiles.
set -o pipefail
set +e +u
set +x
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

NAP_MODE="${1:-}"
if [[ "$NAP_MODE" == --check-only && "$#" == 1 ]]; then
  :
elif [[ "$NAP_MODE" == --install && "$#" == 2 && ( "$2" == mariadb || "$2" == caddy ) ]]; then
  [[ "$EUID" == 0 && -r /run/systemd/container && "$(cat /run/systemd/container)" == lxc ]] || exit 83
  NAP_APPLICATION="$2"
else
  exit 83
fi
[[ -f /.dockerenv || -f /run/systemd/container ]] || exit 83
for nap_tool in pct pvesh pveversion; do
  command -v "$nap_tool" >/dev/null 2>&1 && exit 83
done
command -v curl >/dev/null 2>&1 && command -v ip >/dev/null 2>&1 || exit 83

NAP_HARNESS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 83
[[ -n "${NAP_BUNDLE_ROOT:-}" ]] || exit 83
python3 "$NAP_HARNESS_DIR/spike_community.py" --sources "$NAP_BUNDLE_ROOT" \
  --lock "$NAP_HARNESS_DIR/community-sources.lock.json" >/dev/null 2>&1 || exit 82

NAP_CORE_DIR="$NAP_BUNDLE_ROOT/core"
export NAP_CORE_DIR COMMUNITY_SCRIPTS_CORE_DIR="$NAP_CORE_DIR"
export COMMUNITY_SCRIPTS_CORE_URL=https://raw.githubusercontent.com/community-scripts/core/81a2e2ae7d42dea39fd5dd7903b266b5e607c811
export COMMUNITY_SCRIPTS_URL=https://raw.githubusercontent.com/community-scripts/ProxmoxVE/5d477b0b6efb4141da0b90cadcec32f8641a815c
export COMMUNITY_SCRIPTS_NO_PREFETCH=1 DIAGNOSTICS=no TELEMETRY_CONTEXT=container
export DEV_MODE_TRACE=false VERBOSE=no SSH_ROOT=no PASSWORD=NAP_ROOT_STAYS_LOCKED
unset dev_mode BASH_ENV SSH_AUTHORIZED_KEY RANDOM_UUID

# Cargar sólo definiciones; la política reemplaza logging/traps antes del bootstrap.
source "$NAP_CORE_DIR/core/core.func" >/dev/null 2>&1 || exit 82
source "$NAP_CORE_DIR/core/error_handler.func" >/dev/null 2>&1 || exit 82
NAP_BOOTSTRAPPING=1
source "$NAP_HARNESS_DIR/community_bootstrap_policy.func" || exit 82
FUNCTIONS_FILE_PATH=$(cat "$NAP_CORE_DIR/lxc/install.func"; printf '\n'; cat "$NAP_HARNESS_DIR/community_install_policy.func") || exit 82
if [[ "$NAP_MODE" == --check-only ]]; then
  source /dev/stdin <<<"$FUNCTIONS_FILE_PATH" >/dev/null 2>&1 || exit 82
  _cs_source_func lib/tools.func >/dev/null 2>&1
  declare -f setup_mariadb >/dev/null && declare -f fetch_and_deploy_gh_release >/dev/null || exit 82
  printf '%s\n' '{"state":"core_bootstrap_loaded","profiles_enabled":[],"real_guest_gate_pending":true}'
else
  export app="$NAP_APPLICATION" APP="$NAP_APPLICATION" var_os=debian var_version=13 DISABLEIP6=no
  export var_mariadb_phpmyadmin=no var_caddy_xcaddy=no
  var_appversion=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["caddy"]["version"])' \
      "$NAP_HARNESS_DIR/community-dependencies.lock.json") || exit 82
  export var_appversion
  # No nuevo bash: se conservan los hooks readonly de la política durante source.
  source "$NAP_BUNDLE_ROOT/proxmox/install/${NAP_APPLICATION}-install.sh" >/dev/null 2>&1
fi
