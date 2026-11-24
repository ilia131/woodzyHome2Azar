\set ON_ERROR_STOP on
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
\getenv runtime_password AKSORIA_RUNTIME_PASSWORD
\getenv migration_password AKSORIA_MIGRATION_PASSWORD

BEGIN;
SELECT pg_advisory_xact_lock(679277361);
SELECT 'CREATE ROLE aksoria_runtime' WHERE NOT EXISTS
    (SELECT 1 FROM pg_roles WHERE rolname = 'aksoria_runtime') \gexec
SELECT 'CREATE ROLE aksoria_migration' WHERE NOT EXISTS
    (SELECT 1 FROM pg_roles WHERE rolname = 'aksoria_migration') \gexec
SELECT format('ALTER ROLE aksoria_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L', :'runtime_password') \gexec
SELECT format('ALTER ROLE aksoria_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L', :'migration_password') \gexec
-- Refuse pre-existing granted memberships rather than inheriting or silently rewriting them.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member IN ('aksoria_runtime'::regrole, 'aksoria_migration'::regrole)) THEN
        RAISE EXCEPTION 'Remove existing memberships from the dedicated application roles before provisioning';
    END IF;
END
$$;
SELECT format('ALTER DATABASE %I OWNER TO aksoria_migration', current_database()) \gexec
SELECT format('REVOKE CREATE, TEMP ON DATABASE %I FROM PUBLIC, aksoria_runtime', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO aksoria_runtime', current_database()) \gexec
ALTER SCHEMA public OWNER TO aksoria_migration;
REVOKE CREATE ON SCHEMA public FROM PUBLIC, aksoria_runtime;
GRANT USAGE ON SCHEMA public TO aksoria_runtime;
-- Transfer only application objects in this dedicated database's public schema.
-- Extension-owned objects keep their original owner. Table-owned sequences follow their tables.
SELECT format('ALTER %s %I.%I OWNER TO aksoria_migration',
    CASE c.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
    n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r','p','S','v','m')
  AND c.relowner <> 'aksoria_migration'::regrole
  AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                  AND d.objid = c.oid AND d.deptype IN ('e','a','i'))
ORDER BY (c.relkind = 'S'), c.oid \gexec

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aksoria_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aksoria_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE aksoria_migration IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aksoria_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE aksoria_migration IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aksoria_runtime;
COMMIT;
