"""Ensayos y artefactos 010; esquema congelado, no importa modelos runtime."""
from alembic import op
import sqlalchemy as sa
revision = '010_02_ensayos_artefactos'
down_revision = '010_01_biblioteca'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('ensayos_preparacion',
        sa.Column('incorporacion_id', sa.Uuid(), nullable=False),
        sa.Column('definicion_id', sa.Uuid(), nullable=False),
        sa.Column('perfil_id', sa.String(100), nullable=False),
        sa.Column('estado', sa.String(40), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('execution_generation', sa.Integer(), nullable=False),
        sa.Column('creado_por', sa.Integer(), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('aviso_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('avisado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelada_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cierre_remoto_confirmado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entradas_resueltas', sa.JSON(), nullable=False),
        sa.Column('entradas_sha256', sa.String(64), nullable=True),
        sa.Column('confirmada_por', sa.Integer(), nullable=True),
        sa.Column('confirmada_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('artefacto_id', sa.Uuid(), nullable=True),
        sa.Column('evidencia_id', sa.Uuid(), nullable=True),
        sa.Column('publicacion_id', sa.Uuid(), nullable=True),
        sa.Column('limpieza_estado', sa.String(30), nullable=False),
        sa.Column('motivo_cierre', sa.Text(), nullable=True),
        sa.Column('error_codigo', sa.String(100), nullable=True),
        sa.Column('error_detalle_seguro', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.CheckConstraint("limpieza_estado IN ('no_solicitada','pendiente','en_curso','confirmada','fallida')", name='ck_ensayo_limpieza'),
        sa.CheckConstraint("estado IN ('pendiente','resolviendo','esperando_confirmacion','construyendo','ensayando','lista_para_comprobar','comprobada','fallida','incierta','descartada','vencida')", name='ck_ensayo_estado'),
        sa.CheckConstraint('revision >= 1 AND execution_generation >= 1', name='ck_ensayo_revision'))
    op.create_table('recursos_ensayo',
        sa.Column('ensayo_id', sa.Uuid(), nullable=False),
        sa.Column('rol', sa.String(30), nullable=False),
        sa.Column('identidad_infraestructura_id', sa.Uuid(), nullable=True),
        sa.Column('destino_snapshot', sa.JSON(), nullable=False),
        sa.Column('acceso_metadata', sa.JSON(), nullable=False),
        sa.Column('credenciales_encrypted', sa.Text(), nullable=True),
        sa.Column('ausencia_confirmada_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('ensayo_id', 'rol', name='uq_recurso_ensayo_rol'),
        sa.UniqueConstraint('identidad_infraestructura_id', name=None))
    op.create_table('operaciones_ensayo',
        sa.Column('ensayo_id', sa.Uuid(), nullable=False),
        sa.Column('recurso_id', sa.Uuid(), nullable=True),
        sa.Column('tipo', sa.String(40), nullable=False),
        sa.Column('fase', sa.String(60), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        sa.Column('actor_tipo', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.String(100), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=True),
        sa.Column('job_id', sa.String(200), nullable=True),
        sa.Column('upid', sa.String(300), nullable=True),
        sa.Column('contexto_seguro', sa.JSON(), nullable=False),
        sa.Column('resultado', sa.JSON(), nullable=False),
        sa.Column('intento', sa.Integer(), nullable=False),
        sa.Column('lease_generation', sa.Integer(), nullable=False),
        sa.Column('lease_owner', sa.String(100), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dispatch_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_poll_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_codigo', sa.String(100), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.CheckConstraint("estado IN ('pendiente','en_curso','confirmada','fallida','incierta')", name='ck_operacion_ensayo_estado'),
        sa.UniqueConstraint('ensayo_id', 'idempotency_key', name='uq_operacion_ensayo_clave'))
    op.create_table('eventos_ensayo',
        sa.Column('ensayo_id', sa.Uuid(), nullable=False),
        sa.Column('operacion_id', sa.Uuid(), nullable=True),
        sa.Column('evento_clave', sa.String(200), nullable=False),
        sa.Column('anterior', sa.String(40), nullable=True),
        sa.Column('nuevo', sa.String(40), nullable=False),
        sa.Column('actor_tipo', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.String(100), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('metadata_segura', sa.JSON(), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('ensayo_id', 'evento_clave', name='uq_evento_ensayo_clave'))
    op.create_table('presupuestos_builder',
        sa.Column('scope_id', sa.String(100), nullable=False, primary_key=True),
        sa.Column('revision_config', sa.Integer(), nullable=False),
        sa.Column('limite_bytes', sa.BigInteger(), nullable=False),
        sa.Column('habilitado', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('limite_bytes > 0 AND revision_config >= 1', name='ck_presupuesto_builder_positivo'))
    op.create_table('artefactos_preparados',
        sa.Column('definicion_id', sa.Uuid(), nullable=False),
        sa.Column('entradas_sha256', sa.String(64), nullable=False),
        sa.Column('estado', sa.String(30), nullable=False),
        sa.Column('registro_id', sa.String(100), nullable=False),
        sa.Column('scope_id', sa.String(100), nullable=False),
        sa.Column('volume_id', sa.String(240), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('image_bytes', sa.BigInteger(), nullable=False),
        sa.Column('bundle_sha256', sa.String(64), nullable=False),
        sa.Column('bundle_bytes', sa.BigInteger(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('saneamiento', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('definicion_id', name=None))
    op.create_table('replicas_artefacto',
        sa.Column('artefacto_id', sa.Uuid(), nullable=False),
        sa.Column('nodo', sa.String(100), nullable=False),
        sa.Column('storage_id', sa.String(100), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('bundle_sha256', sa.String(64), nullable=False),
        sa.Column('registro_revision', sa.String(100), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('artefacto_id', 'nodo', 'storage_id', name='uq_replica_destino'))
    op.create_table('reservas_espacio_builder',
        sa.Column('ensayo_id', sa.Uuid(), nullable=False),
        sa.Column('host_id', sa.String(100), nullable=False),
        sa.Column('scope_id', sa.String(100), nullable=False),
        sa.Column('bytes_temporales', sa.BigInteger(), nullable=False),
        sa.Column('bytes_finales_previstos', sa.BigInteger(), nullable=False),
        sa.Column('estado', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('liberado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('ensayo_id', name=None),
        sa.CheckConstraint('bytes_temporales >= 0 AND bytes_finales_previstos >= 0', name='ck_reserva_builder_bytes'))
    op.create_table('publicaciones_oferta',
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('definicion_id', sa.Uuid(), nullable=False),
        sa.Column('ensayo_id', sa.Uuid(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('creado_por', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.UniqueConstraint('template_id', 'revision', name='uq_publicacion_revision'))
    op.add_column('definiciones_servicio', sa.Column('incorporacion_id', sa.Uuid(), nullable=True))
    op.add_column('definiciones_servicio', sa.Column('base_definicion_id', sa.Uuid(), nullable=True))
    op.add_column('definiciones_servicio', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('compromisos_capacidad', sa.Column('recurso_ensayo_id', sa.Uuid(), nullable=True))
    op.add_column('identidades_infraestructura', sa.Column('recurso_ensayo_id', sa.Uuid(), nullable=True))
    op.alter_column('compromisos_capacidad', 'pedido_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key('fk_010_ensayos_preparacion_creado_por', 'ensayos_preparacion', 'usuarios', ['creado_por'], ['id'])
    op.create_foreign_key('fk_ensayo_publicacion', 'ensayos_preparacion', 'publicaciones_oferta', ['publicacion_id'], ['id'])
    op.create_foreign_key('fk_010_ensayos_preparacion_incorporacion_id', 'ensayos_preparacion', 'incorporaciones_aplicacion', ['incorporacion_id'], ['id'])
    op.create_foreign_key('fk_ensayo_artefacto', 'ensayos_preparacion', 'artefactos_preparados', ['artefacto_id'], ['id'])
    op.create_foreign_key('fk_010_ensayos_preparacion_confirmada_por', 'ensayos_preparacion', 'usuarios', ['confirmada_por'], ['id'])
    op.create_foreign_key('fk_010_ensayos_preparacion_definicion_id', 'ensayos_preparacion', 'definiciones_servicio', ['definicion_id'], ['id'])
    op.create_foreign_key('fk_010_ensayos_preparacion_evidencia_id', 'ensayos_preparacion', 'evidencias', ['evidencia_id'], ['id'])
    op.create_index('uq_ensayo_abierto', 'ensayos_preparacion', ['definicion_id'], unique=True, postgresql_where=sa.text("estado NOT IN ('descartada','vencida','fallida') AND publicacion_id IS NULL"))
    op.create_foreign_key('fk_010_recursos_ensayo_ensayo_id', 'recursos_ensayo', 'ensayos_preparacion', ['ensayo_id'], ['id'])
    op.create_foreign_key('fk_recurso_ensayo_identidad', 'recursos_ensayo', 'identidades_infraestructura', ['identidad_infraestructura_id'], ['id'])
    op.create_foreign_key('fk_010_operaciones_ensayo_recurso_id', 'operaciones_ensayo', 'recursos_ensayo', ['recurso_id'], ['id'])
    op.create_foreign_key('fk_010_operaciones_ensayo_ensayo_id', 'operaciones_ensayo', 'ensayos_preparacion', ['ensayo_id'], ['id'])
    op.create_index('uq_operacion_ensayo_builder_abierta', 'operaciones_ensayo', ['ensayo_id'], unique=True, postgresql_where=sa.text("recurso_id IS NULL AND estado IN ('pendiente','en_curso','incierta')"))
    op.create_index('uq_operacion_ensayo_recurso_abierta', 'operaciones_ensayo', ['recurso_id'], unique=True, postgresql_where=sa.text("estado IN ('pendiente','en_curso','incierta')"))
    op.create_foreign_key('fk_010_eventos_ensayo_ensayo_id', 'eventos_ensayo', 'ensayos_preparacion', ['ensayo_id'], ['id'])
    op.create_foreign_key('fk_010_eventos_ensayo_operacion_id', 'eventos_ensayo', 'operaciones_ensayo', ['operacion_id'], ['id'])
    op.create_foreign_key('fk_010_artefactos_preparados_definicion_id', 'artefactos_preparados', 'definiciones_servicio', ['definicion_id'], ['id'])
    op.create_foreign_key('fk_010_artefactos_preparados_scope_id', 'artefactos_preparados', 'presupuestos_builder', ['scope_id'], ['scope_id'])
    op.create_foreign_key('fk_010_replicas_artefacto_artefacto_id', 'replicas_artefacto', 'artefactos_preparados', ['artefacto_id'], ['id'])
    op.create_foreign_key('fk_010_reservas_espacio_builder_scope_id', 'reservas_espacio_builder', 'presupuestos_builder', ['scope_id'], ['scope_id'])
    op.create_foreign_key('fk_010_reservas_espacio_builder_ensayo_id', 'reservas_espacio_builder', 'ensayos_preparacion', ['ensayo_id'], ['id'])
    op.create_index('ix_reserva_builder_scope', 'reservas_espacio_builder', ['scope_id', 'estado'], unique=False)
    op.create_foreign_key('fk_010_publicaciones_oferta_definicion_id', 'publicaciones_oferta', 'definiciones_servicio', ['definicion_id'], ['id'])
    op.create_foreign_key('fk_010_publicaciones_oferta_ensayo_id', 'publicaciones_oferta', 'ensayos_preparacion', ['ensayo_id'], ['id'])
    op.create_foreign_key('fk_010_publicaciones_oferta_template_id', 'publicaciones_oferta', 'recurso_templates', ['template_id'], ['id'])
    op.create_foreign_key('fk_010_publicaciones_oferta_creado_por', 'publicaciones_oferta', 'usuarios', ['creado_por'], ['id'])
    op.create_foreign_key('fk_010_definiciones_servicio_incorporacion_id', 'definiciones_servicio', 'incorporaciones_aplicacion', ['incorporacion_id'], ['id'])
    op.create_foreign_key('fk_010_definiciones_servicio_base_definicion_id', 'definiciones_servicio', 'definiciones_servicio', ['base_definicion_id'], ['id'])
    op.create_foreign_key('fk_010_compromisos_capacidad_recurso_ensayo_id', 'compromisos_capacidad', 'recursos_ensayo', ['recurso_ensayo_id'], ['id'])
    op.create_index('uq_compromiso_ensayo_abierto', 'compromisos_capacidad', ['recurso_ensayo_id'], unique=True, postgresql_where=sa.text('liberado_at IS NULL'))
    op.create_foreign_key('fk_identidad_recurso_ensayo', 'identidades_infraestructura', 'recursos_ensayo', ['recurso_ensayo_id'], ['id'])
    op.create_check_constraint('ck_compromiso_propietario', 'compromisos_capacidad', '(pedido_id IS NOT NULL AND recurso_ensayo_id IS NULL) OR (pedido_id IS NULL AND recurso_ensayo_id IS NOT NULL)')
    op.create_check_constraint('ck_identidad_propietario_ensayo', 'identidades_infraestructura', 'recurso_ensayo_id IS NULL OR (pedido_alta_id IS NULL AND servicio_id IS NULL)')
    op.create_unique_constraint('uq_identidad_ensayo', 'identidades_infraestructura', ['recurso_ensayo_id'])

def downgrade():
    raise RuntimeError('Conservar historia 010; deshabilitar feature o restaurar copia comprobada')
