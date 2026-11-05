"""Configuraciones e intentos 011; aditiva, sin reinterpretar datos anteriores.

DDL congelado: no importa modelos runtime. Downgrade sólo sin datos de 011.
"""
from alembic import op
import sqlalchemy as sa

revision = '011_01_despliegue_aplicaciones'
down_revision = '010_06_acceso_aplicacion'
branch_labels = None
depends_on = None

TABLES = ('configuraciones_despliegue', 'secretos_despliegue', 'intentos_despliegue',
          'consolas_operacion', 'consola_fragmentos', 'reservas_red_aplicacion')
LINKS = ('recurso_templates', 'pedidos', 'servicios')
AGENDA = ('despliegue_solicitado_at', 'despliegue_programado_at',
          'despliegue_revision_programada', 'despliegue_solicitado_por')


def upgrade():
    op.create_table('configuraciones_despliegue',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('codigo', sa.String(100), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('origen', sa.String(30), nullable=False),
        sa.Column('modelo_servicio', sa.String(10), nullable=False),
        sa.Column('documento', sa.JSON(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('perfil_id', sa.String(64), nullable=False),
        sa.Column('perfil_revision', sa.Integer(), nullable=False),
        sa.Column('perfil_sha256', sa.String(64), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='validada'),
        sa.Column('validaciones', sa.JSON(), nullable=False),
        sa.Column('creado_por', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retirada_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('codigo', 'revision', name='uq_configuracion_codigo_revision'),
        sa.CheckConstraint('revision > 0 AND perfil_revision > 0', name='ck_configuracion_revisiones'),
        sa.CheckConstraint("origen IN ('imagen_docker','community_scripts')", name='ck_configuracion_origen'),
        sa.CheckConstraint("modelo_servicio IN ('paas','saas')", name='ck_configuracion_modelo'),
        sa.CheckConstraint("estado IN ('validada','retirada')", name='ck_configuracion_estado'),
        sa.CheckConstraint("(estado = 'validada' AND retirada_at IS NULL) OR (estado = 'retirada' AND retirada_at IS NOT NULL)", name='ck_configuracion_retirada'),
        sa.CheckConstraint('length(sha256) = 64 AND length(perfil_sha256) = 64', name='ck_configuracion_hashes'))
    op.create_table('secretos_despliegue',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('configuracion_id', sa.Uuid(), sa.ForeignKey('configuraciones_despliegue.id'), nullable=False),
        sa.Column('nombre', sa.String(64), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('origen', sa.String(12), nullable=False),
        sa.Column('valor_cifrado', sa.Text(), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('pedido_id', 'nombre', 'revision', name='uq_secreto_pedido_nombre_revision'),
        sa.CheckConstraint('revision > 0', name='ck_secreto_revision'),
        sa.CheckConstraint("origen IN ('generado','aportado')", name='ck_secreto_origen'),
        sa.CheckConstraint('length(nombre) BETWEEN 1 AND 64 AND length(valor_cifrado) > 0', name='ck_secreto_contenido'))
    op.create_index('ix_secretos_despliegue_pedido_id', 'secretos_despliegue', ['pedido_id'])
    op.add_column('operaciones_infraestructura', sa.Column('operacion_raiz_id', sa.Uuid()))
    op.create_foreign_key('fk_operacion_raiz', 'operaciones_infraestructura', 'operaciones_infraestructura', ['operacion_raiz_id'], ['id'])
    op.create_index('ix_operaciones_infraestructura_operacion_raiz_id', 'operaciones_infraestructura', ['operacion_raiz_id'])
    op.create_table('intentos_despliegue',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('operacion_id', sa.Uuid(), sa.ForeignKey('operaciones_infraestructura.id'), nullable=False, unique=True),
        sa.Column('operacion_raiz_id', sa.Uuid(), sa.ForeignKey('operaciones_infraestructura.id'), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('identidad_infraestructura_id', sa.Uuid(), sa.ForeignKey('identidades_infraestructura.id'), nullable=False),
        sa.Column('configuracion_sha256', sa.String(64), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='preparado'),
        sa.Column('runner_job_id', sa.String(100)),
        sa.Column('node_boot_id', sa.Uuid()),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        *[sa.Column(name, sa.DateTime(timezone=True)) for name in ('iniciado_at', 'observado_at', 'terminado_at')],
        sa.Column('ultimo_source_seq', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('error_codigo', sa.String(80)),
        sa.Column('error_detalle_seguro', sa.String(500)),
        sa.UniqueConstraint('operacion_raiz_id', 'numero', name='uq_intento_raiz_numero'),
        sa.UniqueConstraint('operacion_raiz_id', 'id', 'execution_id', name='uq_intento_identidad_consola'),
        sa.CheckConstraint('numero > 0 AND ultimo_source_seq >= 0', name='ck_intento_contadores'),
        sa.CheckConstraint("estado IN ('preparado','ejecutando','confirmado','fallido','incierto')", name='ck_intento_estado'),
        sa.CheckConstraint('length(configuracion_sha256) = 64', name='ck_intento_hash'))
    op.create_index('ix_intentos_despliegue_operacion_raiz_id', 'intentos_despliegue', ['operacion_raiz_id'])
    op.create_table('consolas_operacion',
        sa.Column('operacion_raiz_id', sa.Uuid(), sa.ForeignKey('operaciones_infraestructura.id'), primary_key=True),
        sa.Column('next_seq', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('first_retained_seq', sa.BigInteger(), nullable=False, server_default='1'),
        *[sa.Column(name, sa.BigInteger(), nullable=False, server_default='0') for name in ('last_seq', 'retained_bytes', 'dropped_bytes', 'dropped_messages')],
        sa.Column('last_captured_at', sa.DateTime(timezone=True)),
        sa.Column('last_ingested_at', sa.DateTime(timezone=True)),
        sa.Column('truncated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expired', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ultimo_resultado_seguro', sa.JSON()),
        sa.CheckConstraint('next_seq > 0 AND first_retained_seq > 0 AND last_seq >= 0 AND next_seq = last_seq + 1 AND first_retained_seq <= next_seq', name='ck_consola_secuencia'),
        sa.CheckConstraint('retained_bytes BETWEEN 0 AND 10000000 AND dropped_bytes >= 0 AND dropped_messages >= 0', name='ck_consola_cuota'))
    op.create_table('consola_fragmentos',
        sa.Column('operacion_raiz_id', sa.Uuid(), sa.ForeignKey('consolas_operacion.operacion_raiz_id'), primary_key=True),
        sa.Column('seq', sa.BigInteger(), primary_key=True),
        sa.Column('intento_id', sa.Uuid(), nullable=False),
        sa.Column('execution_id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(10), nullable=False),
        sa.Column('source_key', sa.String(160), nullable=False),
        sa.Column('source_seq', sa.BigInteger()),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fase', sa.String(40), nullable=False),
        sa.Column('stream', sa.String(10), nullable=False),
        sa.Column('texto_depurado', sa.Text(), nullable=False),
        sa.Column('utf8_bytes', sa.Integer(), nullable=False),
        sa.UniqueConstraint('execution_id', 'source', 'source_key', name='uq_consola_evento_productor'),
        sa.ForeignKeyConstraint(['operacion_raiz_id', 'intento_id', 'execution_id'],
            ['intentos_despliegue.operacion_raiz_id', 'intentos_despliegue.id', 'intentos_despliegue.execution_id'], name='fk_consola_intento_identidad'),
        sa.CheckConstraint("(source = 'runner' AND source_seq IS NOT NULL AND source_seq > 0 AND source_key = CAST(source_seq AS VARCHAR)) OR (source = 'portal' AND source_seq IS NULL AND stream = 'sistema')", name='ck_consola_productor'),
        sa.CheckConstraint("stream IN ('sistema','stdout','stderr')", name='ck_consola_stream'),
        sa.CheckConstraint('seq > 0 AND utf8_bytes BETWEEN 1 AND 8192', name='ck_consola_fragmento_limite'),
        sa.CheckConstraint('octet_length(texto_depurado) = utf8_bytes', name='ck_consola_utf8'))
    op.create_index('ix_consola_captura', 'consola_fragmentos', ['captured_at'])
    op.create_table('reservas_red_aplicacion',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('identidad_id', sa.Uuid(), sa.ForeignKey('identidades_infraestructura.id'), nullable=False, unique=True),
        sa.Column('cluster_id', sa.String(80), nullable=False),
        sa.Column('perfil_id', sa.String(64), nullable=False),
        sa.Column('perfil_revision', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.String(64), nullable=False),
        sa.Column('address', sa.String(45), nullable=False),
        sa.Column('mac', sa.String(17), nullable=False),
        sa.Column('host', sa.String(253), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('creada_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('liberada_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('perfil_revision > 0', name='ck_red_revision'))
    op.create_index('uq_red_direccion_activa', 'reservas_red_aplicacion', ['cluster_id', 'address'], unique=True, postgresql_where=sa.text('liberada_at IS NULL'))
    op.create_index('uq_red_slot_activo', 'reservas_red_aplicacion', ['perfil_id', 'slot_id'], unique=True, postgresql_where=sa.text('liberada_at IS NULL'))
    for table in LINKS:
        op.add_column(table, sa.Column('configuracion_despliegue_id', sa.Uuid()))
        op.create_foreign_key(f'fk_{table}_configuracion', table, 'configuraciones_despliegue', ['configuracion_despliegue_id'], ['id'])
        op.create_index(f'ix_{table}_configuracion_despliegue_id', table, ['configuracion_despliegue_id'])
        op.create_check_constraint(f'ck_{table}_origen_exclusivo', table, 'definicion_version_id IS NULL OR configuracion_despliegue_id IS NULL')
    op.add_column('pedidos', sa.Column('despliegue_solicitado_at', sa.DateTime(timezone=True)))
    op.add_column('pedidos', sa.Column('despliegue_programado_at', sa.DateTime(timezone=True)))
    op.add_column('pedidos', sa.Column('despliegue_revision_programada', sa.Integer()))
    op.add_column('pedidos', sa.Column('despliegue_solicitado_por', sa.Integer()))
    op.create_foreign_key('fk_pedido_solicitante_despliegue', 'pedidos', 'usuarios', ['despliegue_solicitado_por'], ['id'])
    op.create_check_constraint('ck_pedido_agenda_revision', 'pedidos', 'despliegue_revision_programada IS NULL OR despliegue_revision_programada > 0')
    op.create_index('ix_pedido_despliegue_programado', 'pedidos', ['despliegue_programado_at'], postgresql_where=sa.text('despliegue_programado_at IS NOT NULL'))
    op.execute("""CREATE FUNCTION nap011_configuracion_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Configuracion inmutable'; END IF;
      IF (to_jsonb(OLD) - ARRAY['estado','retirada_at']) IS DISTINCT FROM
         (to_jsonb(NEW) - ARRAY['estado','retirada_at']) THEN
        RAISE EXCEPTION 'Configuracion inmutable';
      END IF;
      IF (NEW.estado IS DISTINCT FROM OLD.estado OR NEW.retirada_at IS DISTINCT FROM OLD.retirada_at)
         AND NOT (OLD.estado='validada' AND NEW.estado='retirada' AND OLD.retirada_at IS NULL AND NEW.retirada_at IS NOT NULL)
      THEN RAISE EXCEPTION 'Retirada definitiva'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER nap011_configuracion_inmutable BEFORE UPDATE OR DELETE ON configuraciones_despliegue FOR EACH ROW EXECUTE FUNCTION nap011_configuracion_inmutable()')


def downgrade():
    bind = op.get_bind()
    # A downgrade must never silently delete instances, snapshots, logs or secrets.
    if any(bind.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')) for table in TABLES):
        raise RuntimeError('Downgrade rechazado: hay datos 011 que deben conservarse')
    for table, fields in [('operaciones_infraestructura', ['operacion_raiz_id']), ('pedidos', list(AGENDA))]:
        clause = ' OR '.join(f'{f} IS NOT NULL' for f in fields)
        if bind.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table} WHERE {clause})')):
            raise RuntimeError('Downgrade rechazado: hay datos 011 que deben conservarse')
    op.execute('DROP TRIGGER nap011_configuracion_inmutable ON configuraciones_despliegue')
    op.execute('DROP FUNCTION nap011_configuracion_inmutable()')
    op.drop_index('ix_pedido_despliegue_programado', table_name='pedidos')
    op.drop_constraint('ck_pedido_agenda_revision', 'pedidos', type_='check')
    op.drop_constraint('fk_pedido_solicitante_despliegue', 'pedidos', type_='foreignkey')
    for name in reversed(AGENDA): op.drop_column('pedidos', name)
    for table in reversed(LINKS):
        op.drop_constraint(f'ck_{table}_origen_exclusivo', table, type_='check')
        op.drop_constraint(f'fk_{table}_configuracion', table, type_='foreignkey')
        op.drop_index(f'ix_{table}_configuracion_despliegue_id', table_name=table)
        op.drop_column(table, 'configuracion_despliegue_id')
    for table in reversed(TABLES): op.drop_table(table)
    op.drop_index('ix_operaciones_infraestructura_operacion_raiz_id', table_name='operaciones_infraestructura')
    op.drop_constraint('fk_operacion_raiz', 'operaciones_infraestructura', type_='foreignkey')
    op.drop_column('operaciones_infraestructura', 'operacion_raiz_id')
