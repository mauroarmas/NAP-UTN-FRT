# NAP — Nube Académica Privada

Portal para que las cátedras soliciten entornos Linux y aplicaciones, y administración
apruebe y gestione sus instancias en Proxmox. React/Vite, FastAPI, PostgreSQL 16 y LXC.

**Implementación en curso:** [spec 011](specs/011-desplegar-servicios-universitarios/spec.md),
motor de imágenes Docker y aplicaciones de Community Scripts. El motor definitivo
todavía no está habilitado. Draw.io e IaaS conservan el recorrido anterior.

Para continuar desde otra computadora, empezar por
[el traspaso técnico y la copia de datos](docs/traspaso-011.md).

```bash
python3 scripts/traspaso.py init
docker compose -p nap-handoff -f docker-compose.handoff.yml build
docker compose -p nap-handoff -f docker-compose.handoff.yml up -d --wait db
```

Si recibiste una copia de datos, usar `init --keyring /ruta/privada/keyring.json`
en el primer comando, según la guía; esa copia necesita sus claves originales.

Antes de arrancar la API, **elegir** entre restaurar la copia entregada o migrar una
base vacía; ambos recorridos están en la guía. El portal estará en
http://localhost:5174. Este Compose no inicia workers ni conecta a Proxmox.

- [Documentación vigente e histórica](docs/README.md)
- [Instrucciones del proyecto](AGENTS.md) y [constitución](.specify/memory/constitution.md)
- [Backend y pruebas](backend/README.md) · [Frontend y pruebas](frontend/README.md)
- [Instalación operativa](DOCKER.md) — distinta del clon local
- [Prompt para Claude](docs/prompt-continuacion-011.md)
