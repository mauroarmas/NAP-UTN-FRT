-- Ejecutar como propietario tras cada release; nap_runtime_role es un
-- identificador no secreto de rol LOGIN ya creado sin privilegios de dueño.
\set ON_ERROR_STOP on
BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I',current_database(),:'nap_runtime_role') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I',:'nap_runtime_role') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I',:'nap_runtime_role') \gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I',:'nap_runtime_role') \gexec
SELECT format('REVOKE UPDATE, DELETE ON evidencias, bitacora_cierre, pedidos_historial, servicios_historial, eventos_seguridad FROM %I',:'nap_runtime_role') \gexec
SELECT format('REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM %I',:'nap_runtime_role') \gexec
SELECT format('REVOKE INSERT, UPDATE, DELETE ON restauraciones FROM %I',:'nap_runtime_role') \gexec
SELECT format('REVOKE INSERT, DELETE ON accesos_iniciales_restaurados FROM %I',:'nap_runtime_role') \gexec
SELECT format('REVOKE UPDATE, DELETE ON eventos_ensayo, publicaciones_oferta FROM %I',:'nap_runtime_role') \gexec
COMMIT;

-- 010: aplicar después de la migración, con el mismo rol DML institucional.
