# Security Policy

## Reporting

Do not open a public issue for a suspected vulnerability that exposes credentials,
private prompts, user files, or an exploitable deployment detail. Contact the
repository owner privately and include a minimal reproduction, affected version,
impact, and suggested mitigation when available.

## Deployment responsibilities

Aether is self-hosted software. Operators are responsible for:

- generating unique application and database secrets;
- restricting PostgreSQL, Redis, model APIs, image services, and sandboxes;
- terminating TLS and configuring trusted reverse-proxy headers;
- reviewing registration, sharing, quotas, plugins, skills, and tool approvals;
- securing uploads, generated files, backups, and persistent model directories;
- applying dependency and operating-system security updates; and
- rotating any credential that may have appeared in a log, backup, image, or commit.

Never publish a notebook or container image until accounts, conversations, provider
records, files, logs, shell histories, caches, and deployment keys have been removed.

## Supported versions

Security fixes target the latest revision of the default branch. Older snapshots
should be upgraded before being exposed to untrusted networks.

## Secret handling

Provider credentials are encrypted at rest with `SECRET_KEY`. The encryption key
must be stored outside source control. Changing it invalidates existing encrypted
provider values. Git history is not a secret store: if a secret is committed, revoke
it first, then remove it from history.
