# Secure deployment and operations

The verified deliverable is a local, single-process prototype. The following is a deployment plan and container recipe, not a claim of completed production deployment.

## Local container option

```bash
docker build -t northstar-advisory .
docker volume create northstar-data
docker run --rm --name northstar \
  -p 127.0.0.1:8000:8000 \
  -v northstar-data:/app/data \
  northstar-advisory
```

The container runs as a non-root user and keeps SQLite on a persistent volume. These commands use demo mode on loopback. Docker was not available for verification in this session; validate the build, volume ownership and health check on the target host.

## Before exposing a service

Put an HTTPS reverse proxy or load balancer in front of a private application listener. Use `APP_DEMO=0`, `COOKIE_SECURE=1`, unique `ADMIN_PASSWORD` and `USER_PASSWORD` values of at least 14 characters, and an `ALLOWED_HOSTS` list matching the actual hostname plus `127.0.0.1` for the health check. Use a fresh production database without seeded synthetic records. Non-demo initialization replaces known demo password hashes if migrating an existing demo database and invalidates those users' sessions, but a fresh database is preferred.

Inject secrets through the host's secret manager. Never pass API keys to the browser or put them into source control. Ensure the reverse proxy provides the correct scheme/host and configure Uvicorn to trust forwarded headers only from the proxy. Set request-body limits and request timeouts there too. Review data processing and provider retention before enabling AI on real business material.

Replace the two local accounts with SSO/OIDC and MFA; add account lifecycle management, password rotation, separate role administration and revocable document grants. Keep authorization before all retrieval and tool access when migrating to a vector store. Derive identity from the trusted server session, not query parameters or model output. Test tenant boundaries before adding multiple organizations.

Move parsers into resource-limited worker processes with CPU/memory/time limits, safe XML handling, malware scanning and stricter archive inspection. Current upload limits are not a complete defense against malicious files. Use a maintained dependency scanner and rebuild patched images regularly.

## Monitor

- Poll `/healthz` for database availability; alert on sustained failures and application restarts.
- Collect HTTP status counts, request latency, login failures, unauthorized access events, provider fallback frequency and job failure/age/attempt counts. Audit event metadata is available to admins; production metrics export is future work.
- Keep provider credentials and document content out of logs. Define retention, log access and deletion rules. Forward security audit events to an external append-only store if tamper evidence is required.
- Add per-user/provider quotas and stronger distributed rate limiting before increasing traffic. Current limits are intentionally simple SQLite checks for a small demonstration.

## Maintain and recover

Use encrypted disks, restrictive file permissions, managed backups and a retention policy. Back up SQLite with its online backup API or stop the process before a consistent snapshot; copying only a live `.db` file can miss WAL data. Test a restore in a separate environment. Original binaries are not kept, so retain approved source files elsewhere if required.

After a release, run the automated suite and repeat an admin/standard access test. Check pending/failed automation records. Current pending/interrupted jobs resume on restart; failed jobs need an administrator retry. Add schema migrations and a rollback plan before changing persistent structures.

## Expand

Move SQLite to PostgreSQL for higher concurrency and use an external queue with retries, backoff, dead-letter records and idempotency keys. Add object storage for originals and a delivery outbox if implementing email/webhook notifications. Give each notification the source document's confidentiality classification.

Add embeddings and optional reranking for paraphrases, preserving authorization filters before candidate selection. Evaluate with a broader question set containing missing evidence, misleading instructions and adversarial access requests. Add document ownership, versioning and explicit precedence metadata for policies; do not decide policy authority from recency alone. Add reviewed finance schemas, accounting scopes, fiscal calendars and approved FX sources before supporting broader analytics.
