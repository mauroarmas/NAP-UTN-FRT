# Graph Report - .  (2026-08-03)

## Corpus Check
- 100 files · ~60,334 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 618 nodes · 1225 edges · 44 communities (29 shown, 15 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 83 edges (avg confidence: 0.73)
- Token cost: 0 input · 458,745 output

## Community Hubs (Navigation)
- Alembic DB Migrations
- Frontend App Shell & Routing
- Auth & 2FA Backend
- Backend Python Dependencies
- PS Interview: Software Architecture Decisions
- Frontend NPM Dependencies
- Speckit Prerequisite Check Scripts
- Speckit Command Suite & Constitution Rules
- ProxmoxClient API Wrapper
- Catedras (Tenant) API Endpoints
- Pedidos (Orders) API Endpoints
- User Auth Dependencies & Container Listing
- Servicios (Services) API Endpoints
- Templates API Endpoints
- PS Interview: Infrastructure & Tenant Model
- Backend App Config & Startup
- Frontend Icon Sprite Sheet
- Frontend Lint Config
- Servicio Pydantic Schemas
- Get Current User Endpoint
- PS Plan: HA & Network Segmentation
- PS Plan: Deployment & Dev Methodology
- PS Reglamento: Evaluation Roles
- LXC Container Deletion
- LXC Status Retrieval
- Cluster Node Listing
- PS Plan: PaaS/SaaS Inspiration
- PS Plan: AWS-style Order Flow
- PedidoManager State Transitions
- QuotaManager Deployment Checks
- PS Plan: Software Deployment Target
- PS Plan: Infra Methodology Note
- PS Plan: Storage Methodology Note
- PS Plan: Storage & Backup Objective
- Frontend App Favicon
- Frontend Hero Image
- Vite React Scaffold Logo
- Vite Scaffold Logo

## God Nodes (most connected - your core abstractions)
1. `Usuario` - 66 edges
2. `ProxmoxClient` - 26 edges
3. `Base` - 21 edges
4. `Servicio` - 17 edges
5. `RolUsuario` - 16 edges
6. `get_proxmox_client()` - 15 edges
7. `speckit-constitution command` - 15 edges
8. `get_current_user()` - 13 edges
9. `PS Work Plan: Proxmox VE Cluster with High Availability` - 13 edges
10. `PS Work Plan: Management & Orchestration Software` - 13 edges

## Surprising Connections (you probably didn't know these)
- `python-multipart (dependency)` --references--> `Templates/Catalog module (catalog)`  [AMBIGUOUS]
  backend/requirements.txt → docs/implementation_plan.md
- `Frontend stack: React + Vite + TanStack Query + Shadcn/ui` --semantically_similar_to--> `React + Vite template (create-vite)`  [INFERRED] [semantically similar]
  docs/implementation_plan.md → frontend/README.md
- `speckit-specify command` --shares_data_with--> `Checklist Template`  [INFERRED]
  .claude/skills/speckit-specify/SKILL.md → .specify/templates/checklist-template.md
- `api service (FastAPI backend container)` --shares_data_with--> `FastAPI (dependency)`  [INFERRED]
  docker-compose.yml → backend/requirements.txt
- `SQLAlchemy (dependency)` --shares_data_with--> `Data model (ER diagram: Catedra, Usuario, Pedido, Servicio, Metrica)`  [INFERRED]
  backend/requirements.txt → docs/implementation_plan.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Spec-Driven Development command chain (specify -> clarify -> plan -> tasks -> implement -> converge -> analyze)** — _claude_skills_speckit_specify_skill_speckitspecify, _claude_skills_speckit_clarify_skill_speckitclarify, _claude_skills_speckit_plan_skill_speckitplan, _claude_skills_speckit_tasks_skill_speckittasks, _claude_skills_speckit_implement_skill_speckitimplement, _claude_skills_speckit_converge_skill_speckitconverge, _claude_skills_speckit_analyze_skill_speckitanalyze [EXTRACTED 1.00]
- **Shared before/after extension-hook check pattern across all speckit commands** — _claude_skills_speckit_analyze_skill_speckitanalyze, _claude_skills_speckit_checklist_skill_speckitchecklist, _claude_skills_speckit_clarify_skill_speckitclarify, _claude_skills_speckit_constitution_skill_speckitconstitution, _claude_skills_speckit_converge_skill_speckitconverge, _claude_skills_speckit_implement_skill_speckitimplement, _claude_skills_speckit_plan_skill_speckitplan, _claude_skills_speckit_specify_skill_speckitspecify, _claude_skills_speckit_tasks_skill_speckittasks, _claude_skills_speckit_taskstoissues_skill_speckittaskstoissues, _claude_skills_speckit_analyze_skill_extensionsyml [EXTRACTED 1.00]
- **Constitution consistency propagation to plan/spec/tasks templates** — _claude_skills_speckit_constitution_skill_speckitconstitution, _specify_templates_plan_template_plantemplate, _specify_templates_spec_template_spectemplate, _specify_templates_tasks_template_taskstemplate, _specify_memory_constitution_projectconstitution [EXTRACTED 1.00]
- **Three complementary PS practices forming one joint UTN FRT private-cloud project** — docs_plandetrabajo1_titulo, docs_plandetrabajo2_titulo, docs_plandetrabajo3_titulo [INFERRED 0.85]
- **FastAPI backend modules wired to the central API Gateway/Router** — docs_implementation_plan_modulo_auth, docs_implementation_plan_modulo_pedidos, docs_implementation_plan_modulo_orquestacion, docs_implementation_plan_modulo_tenants, docs_implementation_plan_modulo_catalog, docs_implementation_plan_modulo_monitoring, docs_implementation_plan_modulo_mikrotik [EXTRACTED 1.00]
- **PS regulation and template governing the three concrete work plans** — docs_docspracticasupervisad_1094_24_reglamento_de_ps_plan_de_trabajo, docs_docspracticasupervisad_modeloplandetrabajops_estructura, docs_plandetrabajo1_titulo, docs_plandetrabajo2_titulo, docs_plandetrabajo3_titulo [INFERRED 0.75]
- **Infrastructure stack: networking, virtualization nodes, and storage** — graphify_out_transcripts_audio_entrevista_proxmox, graphify_out_transcripts_audio_entrevista_mikrotik, graphify_out_transcripts_audio_entrevista_truenas [EXTRACTED 1.00]
- **Multi-tenant access model: cátedra spaces, predefined roles, and admin panel** — graphify_out_transcripts_audio_entrevista_software_orquestador, graphify_out_transcripts_audio_entrevista_catedra, graphify_out_transcripts_audio_entrevista_roles, graphify_out_transcripts_audio_entrevista_admin_panel [INFERRED 0.75]

## Communities (44 total, 15 thin omitted)

### Community 0 - "Alembic DB Migrations"
Cohesion: 0.05
Nodes (78): Run migrations in 'offline' mode., Run migrations in 'online' mode., run_migrations_offline(), run_migrations_online(), Base, get_db(), Dependency que provee una sesión de base de datos por request., Catedra (+70 more)

### Community 1 - "Frontend App Shell & Routing"
Cohesion: 0.06
Nodes (47): plugins, App(), Sidebar(), Catedras(), Dashboard(), Login(), fmtBytes(), fmtTime() (+39 more)

### Community 2 - "Auth & 2FA Backend"
Cohesion: 0.06
Nodes (58): login(), AsyncSession, post, Genera un nuevo secreto TOTP para configurar 2FA., Verifica un código TOTP y activa 2FA para el usuario., Registra un nuevo usuario. Solo administradores., Login con usuario y contraseña. Devuelve JWT token., register_user() (+50 more)

### Community 3 - "Backend Python Dependencies"
Cohesion: 0.06
Nodes (45): Alembic (dependency), asyncpg (dependency), FastAPI (dependency), passlib (dependency), proxmoxer (dependency), pydantic-settings (dependency), pyotp (dependency), python-jose (dependency) (+37 more)

### Community 4 - "PS Interview: Software Architecture Decisions"
Cohesion: 0.06
Nodes (43): Authentication: username + password + 2FA, nap.frt domain pointing to the portal, Software as middleware/intermediary portal, Proxmox as the software's back-end; users never touch it directly, Division of team roles (infra/storage/software), VMID handled internally, no per-cátedra range, Five-node Proxmox cluster, Minimum workload 150/200 hours (§10) (+35 more)

### Community 5 - "Frontend NPM Dependencies"
Cohesion: 0.06
Nodes (31): axios, dependencies, axios, react, react-dom, react-router-dom, recharts, devDependencies (+23 more)

### Community 6 - "Speckit Prerequisite Check Scripts"
Cohesion: 0.09
Nodes (14): check-prerequisites.sh script, check_dir(), check_file(), get_feature_paths(), get_repo_root(), has_jq(), _persist_feature_json(), resolve_specify_init_dir() (+6 more)

### Community 7 - "Speckit Command Suite & Constitution Rules"
Cohesion: 0.22
Nodes (28): check-prerequisites.sh script, extensions.yml (extension hooks config), speckit-analyze command, speckit-checklist command, "Unit Tests for English" checklist philosophy, speckit-clarify command, speckit-constitution command, Append-only, never-rewrite operating constraint (+20 more)

### Community 8 - "ProxmoxClient API Wrapper"
Cohesion: 0.07
Nodes (14): ProxmoxClient, Obtiene el próximo VMID disponible en el clúster., Obtiene el estado de un nodo específico., Lista todos los contenedores LXC de un nodo., Crea un contenedor LXC. Proxmox asigna el VMID automáticamente., Inicia un contenedor LXC., Detiene un contenedor LXC., Lista todas las VMs QEMU de un nodo. (+6 more)

### Community 9 - "Catedras (Tenant) API Endpoints"
Cohesion: 0.17
Nodes (19): actualizar_catedra(), crear_catedra(), listar_catedras(), obtener_catedra(), AsyncSession, get, patch, post (+11 more)

### Community 10 - "Pedidos (Orders) API Endpoints"
Cohesion: 0.12
Nodes (20): cambiar_estado_pedido(), crear_nuevo_pedido(), listar_pedidos(), obtener_estados(), obtener_pedido(), AsyncSession, get, patch (+12 more)

### Community 11 - "User Auth Dependencies & Container Listing"
Cohesion: 0.20
Nodes (14): Usuario, get_current_user(), Dependency: obtiene el usuario actual a partir del JWT token., Dependency: requiere rol de administrador., require_admin(), listar_contenedores(), listar_nodos(), proxmox_status() (+6 more)

### Community 12 - "Servicios (Services) API Endpoints"
Cohesion: 0.15
Nodes (16): desplegar(), detener(), eliminar(), estado_en_proxmox(), listar_servicios(), obtener_servicio(), AsyncSession, delete (+8 more)

### Community 13 - "Templates API Endpoints"
Cohesion: 0.21
Nodes (13): crear_template(), listar_templates(), obtener_template(), AsyncSession, get, post, Lista los templates disponibles. Todos los usuarios autenticados pueden verlos., Obtiene un template por ID. (+5 more)

### Community 14 - "PS Interview: Infrastructure & Tenant Model"
Cohesion: 0.16
Nodes (15): Admin Panel, AWS (referenced as design inspiration), Cátedra (tenant/user space model), Contenedores Proxmox (containers 100-999 per cátedra), Grupo de WhatsApp (team coordination), MikroTik, Monitoreo de Recursos (resource monitoring), Plantillas de Servidores/Contenedores (size templates) (+7 more)

### Community 15 - "Backend App Config & Startup"
Cohesion: 0.21
Nodes (8): get_settings(), Settings, health_check(), lifespan(), get, Startup y shutdown de la aplicación., root(), BaseSettings

### Community 16 - "Frontend Icon Sprite Sheet"
Cohesion: 0.29
Nodes (7): Bluesky Icon, Discord Icon, Documentation Icon, GitHub Icon, Social (Share/Contact) Icon, icons.svg (Sprite Sheet), X (Twitter) Icon

### Community 17 - "Frontend Lint Config"
Cohesion: 0.33
Nodes (5): rules, react/only-export-components, react/rules-of-hooks, $schema, warn

### Community 18 - "Servicio Pydantic Schemas"
Cohesion: 0.67
Nodes (3): DesplegarRequest, BaseModel, ServicioResponse

### Community 20 - "Get Current User Endpoint"
Cohesion: 0.67
Nodes (3): get_me(), get, Devuelve la información del usuario autenticado.

### Community 21 - "PS Plan: HA & Network Segmentation"
Cohesion: 0.67
Nodes (3): High Availability (HA) concept, Two-network segmentation (storage + compute), General objective: 5-node Proxmox cluster with HA and network segmentation

### Community 22 - "PS Plan: Deployment & Dev Methodology"
Cohesion: 0.67
Nodes (3): Software deployed as LXC container or separate node, Local development environment (nested-virtualization Proxmox VM), Incremental & iterative software methodology

### Community 23 - "PS Reglamento: Evaluation Roles"
Cohesion: 0.67
Nodes (3): Role: Docente Supervisor, Evaluation: Tribunal Evaluador, Planilla, Acta (§7,14,15), Role: Tutor Institución/Empresa

## Ambiguous Edges - Review These
- `python-multipart (dependency)` → `Templates/Catalog module (catalog)`  [AMBIGUOUS]
  backend/requirements.txt · relation: references

## Knowledge Gaps
- **100 isolated node(s):** `common.sh script`, `$schema`, `oxc`, `react/rules-of-hooks`, `warn` (+95 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `python-multipart (dependency)` and `Templates/Catalog module (catalog)`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `Usuario` connect `User Auth Dependencies & Container Listing` to `Alembic DB Migrations`, `Auth & 2FA Backend`, `Catedras (Tenant) API Endpoints`, `Pedidos (Orders) API Endpoints`, `Servicios (Services) API Endpoints`, `Templates API Endpoints`, `Get Current User Endpoint`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Why does `ProxmoxClient` connect `ProxmoxClient API Wrapper` to `Alembic DB Migrations`, `User Auth Dependencies & Container Listing`, `Backend App Config & Startup`, `LXC Container Deletion`, `LXC Status Retrieval`, `Cluster Node Listing`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `get_proxmox_client()` connect `Alembic DB Migrations` to `ProxmoxClient API Wrapper`, `User Auth Dependencies & Container Listing`, `Servicios (Services) API Endpoints`, `Backend App Config & Startup`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `Usuario` (e.g. with `Base` and `ServicioConMetrica`) actually correct?**
  _`Usuario` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Base` (e.g. with `Catedra` and `MetricaSnapshot`) actually correct?**
  _`Base` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `Servicio` (e.g. with `Base` and `ServicioConMetrica`) actually correct?**
  _`Servicio` has 3 INFERRED edges - model-reasoned connections that need verification._