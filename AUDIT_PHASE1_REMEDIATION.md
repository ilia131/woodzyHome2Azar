# HomeAksoria Phase 1 high-severity remediation

## Scope and assessment

This change addresses H1 and H2 from AUDIT_PHASE1_FINAL.md. Neither payment
integration nor the outstanding medium/low findings was part of the work.
Readiness remains **READY AFTER FIXES** until complete Compose restarts on fresh
and existing volumes are proven on a runner with sufficient storage. No
production readiness or load-capacity claim is made.

## H1 — Stale absolute stock adjustment

Previously serialization of writes did not authenticate the freshness of the
operator's absolute target. An approved reservation followed by a stale absolute
write could put already-held units back into the sellable balance.

The client now obtains `stock_revision` from the admin product representation.
An absolute edit submits `stock_revision` on the product PATCH or
`expected_revision` with `target` and `operation_id` on the adjustment endpoint.
Inventory takes the product row lock inside an atomic transaction, compares
the latest ProductChange revision, computes delta from the locked value,
validates the available and reserved range, and records the movement and audit
atomically. An invalid/stale revision returns HTTP 409. Negative target input
is rejected. The counter remains sellable inventory. Signed delta requests
continue to work. A matching UUID retry on a successful dedicated absolute
adjustment returns the original movement; changed parameters on that product
are rejected. Existing UUID scope is still per product (audit M1). A dedicated
absolute request that changes nothing returns 409 without a movement.

The production-path stock search located writers in `orders/inventory.py`
and the existing-product Django admin stock reload in `products/admin.py`.
Checkout and expiration use the service. Catalog API creation records opening
stock via the service. Catalog PATCH routes stock through the service, and
Django admin existing stock remains read-only. Native admin creation records
initial stock in the same transaction. Tests and historical migrations still
contain fixture or migration values. Direct ORM/raw SQL maintenance remains
outside the application stock API and can bypass service-level ledger behavior
as documented in audit M2.

## H2 — PostgreSQL least privilege

The existing runtime and migration job used the image bootstrap superuser.
Compose now explicitly configures `aksoria_runtime` for Web, Worker, Beat and
`aksoria_migration` for the opt-in `init` deployment profile. Secrets are
distinct. Neither application role has SUPERUSER, CREATEDB or CREATEROLE.
Runtime owns neither the database nor public schema. Migration owns the
database, public schema and application tables/sequences, so it can migrate
without superuser. Runtime receives CONNECT, schema USAGE, required table DML
and sequence access. The migration job revokes runtime writes to the Django
migration table. Normal Compose startup excludes the deployment profile;
`./start` explicitly runs the migration job before starting services.

The transition is described in deploy/POSTGRESQL.md. It retains the existing
named volume and bootstrap credentials, refuses unexpected memberships and
transfers application objects without moving extension-owned objects.
The existing database retained OID 16384, all 55 migration records and the
same five auth-group records with digest 853d04c4507c678422af62a87a6056d7. It
had zero products and orders at inspection, so this is preservation evidence
for the existing database and observed records, not a populated order restore.
No existing database or volume was recreated.

## Verification

| Check | Actual result |
| --- | --- |
| Full PostgreSQL/Redis test suite | 98 tests passed twice. Final run: `Ran 98 tests in 16.318s` / `OK`. The final run used the same PostgreSQL/Redis services via a local relay and a disposable test database. |
| Concurrency and inventory | Regression tests cover a stale absolute edit concurrent with checkout, simultaneous absolute edits, ledger delta, UUID replay, negative target, and catalog routing. Existing reservation, cancellation and expiration tests passed. |
| Runtime SQL privileges | PostgreSQL flags `rolsuper=f, rolcreatedb=f, rolcreaterole=f`; schema/database ownership checks false. Real TCP authentication and insert/select/update/delete with rollback succeeded. CREATE ROLE, CREATE DATABASE and ALTER SCHEMA OWNER each returned SQLSTATE `42501`. |
| Migration privileges and existing volume | Migration role flags all false and database owner transferred from bootstrap to migration. Deployment job completed with `No migrations to apply.` under the migration role on the existing volume. |
| Empty database migrations | A new isolated database on the same PostgreSQL cluster was provisioned and the migration role applied all migrations and role seeds. This verifies fresh database initialization, not a fresh full Compose stack. |
| Application configuration | Resolved Compose config asserted Web/Worker/Beat select runtime, init selects migration, and bootstrap/migration passwords differ from runtime. No credential values were printed. |
| Django, migrations and OpenAPI | `System check identified no issues (0 silenced).`; migration state check passed; `No changes detected`; schema validation passed with warnings treated as errors. |
| PostgreSQL and Redis | PostgreSQL 17.12, Redis 7.4.12; database and Redis containers healthy, Redis returned `PONG`. |
| Full Compose runtime | Blocked by Docker VFS storage exhaustion during app container creation. Web, Worker, Beat and gateway were not restored in the audit stack during this check. Existing PostgreSQL volume and data were preserved. No fresh-volume Compose health claim. |

A separate Worker and Beat process using the runtime credentials, the fresh
isolated database and a dedicated Redis broker DB were verified outside Compose.
Worker returned `pong`. Beat dispatched `expire-inventory` and Worker logged
`orders.tasks.expire_reservations ... succeeded ...: 0` on the empty database.
This does not verify post-cutover container networking or healthchecks.

## Changed files

- Application: orders/inventory.py, orders/admin_api.py, products/admin_api.py.
- Regression tests: orders/test_stock_revision.py, products/tests.py. The
  existing product test now submits the required revision and retains all its
  original assertions.
- Deployment: docker-compose.yml, start, .env.example, deploy/provision-db,
  deploy/provision-db.sql, deploy/verify-db-roles.
- Documentation: README.md, AUDIT.md, deploy/POSTGRESQL.md and this report.

No historical Django migration was edited and no new schema migration was
needed. Once adequate disk space is available, rebuild and verify both Compose
profiles before declaring deployment complete.
