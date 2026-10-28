# Perfil base del motor Docker — Feature 011 (T044)

Fecha: 28/10/2026  
Rama: `011-desplegar-servicios-universitarios`  
Artefactos del repositorio:
- `infra/applications/profiles/docker/ubuntu24.json`
- `infra/applications/docker/runtime.py`
- `infra/applications/docker/deploy.py`
- `infra/applications/docker/access.py`
- `infra/applications/docker/probes.py`

---

## 1. Definición de `infra/applications/profiles/docker/ubuntu24.json`

- **Esquema**: `nap-docker-runtime/1`
- **Estado por defecto en el repositorio**: `pendiente_validacion` (ningún módulo del repositorio certifica o habilita perfiles por sí solo).
- **Base LXC**:
  - `os`: `ubuntu`, `version`: `24.04`, `arquitectura`: `amd64`
  - `volumen_lxc`: `local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst`
  - `sha256`: `75a827c4ea4b2bef42e0521f51ed869e398f56b0e6b131c3cd5d284a2e0e08b5`
- **Paquetes fijados del motor anidado**:
  - `docker`: `29.1.3-0ubuntu3~24.04.2`
  - `containerd`: `2.2.1-0ubuntu1~24.04.4`
  - `runc`: `1.3.4-0ubuntu1~24.04.1`
- **Almacenamiento y recursos**:
  - `storage_driver`: `overlayfs` sobre `filesystem`: `ext4`
  - `minimum_resources`: `{"vcpus": 2, "ram_mb": 1024, "disk_gb": 8}` (tamaño `Medium`)
  - `features`: `["nesting=1", "keyctl=1"]` sobre LXC no privilegiado (`unprivileged=true`, `apparmor=enforce`, `seccomp=true`)
- **Borde TLS interno (`edge`)**:
  - `repositorio`: `docker.io/library/caddy`
  - `manifest_digest`: `sha256:d8c17a862962def15cde69863a3a463f25a2664942eafd7bdbf050e9c3116b83`
  - `config_digest`: `sha256:aac61abc4024c323602ccb9ee38bd68b147601f518626b2a055e06944e01c510`

---

## 2. Huella de paquete (`policy_digest()`)

`infra/applications/docker/runtime.py::policy_digest()` calcula el digest SHA-256 canónico de todos los módulos del motor (`job/*.py`, `docker/*.py`, `profiles/docker/ubuntu24.json`, `schemas/nap-deployment-1.json`, `runner/node_executor.py` y `profiles/profile_contract.py`).

- **Digest canónico actual del repositorio y nodo**: `73e804b60ce027506da11c9b8ad549c0b361de8df397b8214d5f0bd4a8eab2c2`.

---

## 3. Regla de habilitación y validación real (Constitución v4.2.0)

Tras aprobar la compuerta real en Proxmox (`T050`/`T109`) con `infra/laboratorio/011/validar_motor_docker.py` para `docker.io/traefik/whoami` (`execution_id: 4bba6281-3a9a-40ef-891d-49e122729537`) y `172.16.36.1:5443/nap/campus-demo` (`execution_id: d07d3250-aba2-463f-8ce6-b8c20e7e806c`), el perfil `docker-ubuntu24:1` (`sha256: 2ed42514102e2f2ed7702bf4f1162f4ba2b6c175f2012f929c0895e743f67a24`, plataforma `{"pve": "9.2.2", "kernel": "7.0.2-6-pve", "arquitectura": "amd64"}`) quedó habilitado de forma idéntica en `/etc/nap/applications-011/runner.json` (nodo) y `/home/mauro/.local/share/nap010/privado/settings.json` (portal).

