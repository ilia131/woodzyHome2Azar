# PostgreSQL deployment

Web, Worker and Beat use `aksoria_runtime`. The explicit migration job uses
`aksoria_migration`. Both roles lack SUPERUSER, CREATEDB, CREATEROLE,
REPLICATION and BYPASSRLS. The migration role owns the database, public schema
and application objects. Runtime has CONNECT, schema USAGE, application-table
DML and sequence access. Django migration records are read-only after the
release job. The bootstrap account is configured only for PostgreSQL itself.

## Existing volume transition

1. Back up the database. Inspect current database and schema owners, role
   memberships, table owners and representative record counts. Provisioning
   targets a dedicated HomeAksoria database with application tables in public.
   Review custom objects and unrelated schemas separately. Extension-owned
   objects keep their owners.
2. Keep the original bootstrap username/password, Compose project name and
   PostgreSQL volume. Schedule downtime for old app writers. Run `./start` to
   append missing secrets, build, stop app writers, provision roles, apply
   migrations and start runtime services. Use shell-compatible dotenv entries.
3. Compare the same database identifier, schema and representative data and run
   `./deploy/verify-db-roles`. It probes runtime CRUD with rollback (one sequence
   value may advance), and expects permission denial for CREATE ROLE, CREATE
   DATABASE and schema ownership changes. Also checks service login identities.
4. Check the migration state and Celery with `docker compose exec web python
   manage.py migrate --check` and `docker compose exec worker celery -A
   config.celery inspect ping`. Inspect Beat and Worker logs for the scheduled
   expiration run.

The repeatable bootstrap command is `./deploy/provision-db`. It uses the
standard image's local bootstrap connection, refuses unexpected application-role
memberships and passes passwords over stdin. Keep shell tracing off. Do not
publish the resolved Compose configuration because it includes secrets.
External PostgreSQL requires equivalent DBA provisioning and extension review.

## Explicit deployment migration

With PostgreSQL started, roles provisioned, and app writers stopped as required
for the release, run:

```sh
docker compose run --rm --no-deps init
```

Normal `docker compose up` does not run the opt-in deployment job. Test against
a dedicated PostgreSQL server or database namespace with a separate test role
allowed to create test databases and a dedicated Redis logical database.
Runtime cannot create test databases.
