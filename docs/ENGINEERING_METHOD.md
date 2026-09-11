# Yggdrasil Standing Engineering Method

This document is a standing project instruction for all future Yggdrasil / Noeron engineering work and must be carried into future continuation notes and handoff bundles.

## Primary roles

### GitHub — primary engineering and CI execution environment

Use GitHub as the default environment for durable engineering work, including:

- source development and code review;
- commits, branches, pull requests, and engineering history;
- long-running regression suites;
- GitHub Actions CI matrices;
- compile/static/security audits;
- authority and release-identity audits;
- package construction and fresh-extract replay;
- hashes, manifests, OpenAPI inventories, and certification evidence;
- durable logs and CI artifacts;
- recovery and continuation metadata.

Prefer GitHub Actions over short-lived local execution for long certification/regression work, especially when local tool timeouts could create ambiguous results. Split heavy suites into bounded/matrix jobs so individual slow tests cannot obscure the overall verdict.

### Google Drive — byte-exact release/archive backup

Use Google Drive as the durable binary/archive backup for:

- certified source TARs;
- installation ZIPs;
- exact ancestor->successor patches;
- final handoff bundles;
- certification manifests/ledgers/evidence bundles;
- detailed live-verification sheets;
- complete API command references;
- standalone continuation checkpoints.

For important release artifacts, upload and then read back/download and recompute hashes when practical. Successful upload alone is not the strongest evidence.

### Hetzner live server — canonical live Yggdrasil substrate

Use the Hetzner server only for genuine live deployment and verification against Yggdrasil's canonical persistent state, including:

- `/opt/noeron/app` promotion/rollback;
- canonical `/var/lib/noeron/noeron.sqlite3` continuity checks;
- systemd/service restart and listener verification;
- loopback/private API verification on port 8741;
- held-out live behavior checks;
- post-restart persistence/continuity checks.

Do not copy the canonical live database into GitHub merely to simplify CI.

### Local ChatGPT/container execution — short exploratory work

Use local execution mainly for:

- quick inspection;
- small code probes;
- bounded experiments;
- artifact preparation;
- small validation steps.

Do not make local short-run tooling the default for long certification suites when GitHub Actions can execute them more reliably and durably.

## Security and authority boundaries

Never commit or upload to GitHub merely for engineering convenience:

- canonical live SQLite state;
- `.env` files containing secrets;
- SSH private keys;
- owner/device tokens;
- credentials;
- unsanitized private microphone/camera payloads;
- private owner conversation exports;
- other secret/private modality state.

Repository carrier commits/trees may differ from frozen runtime source identities because CI, documentation, evidence indexes, or recovery material can exist in the carrier. Never relabel a GitHub carrier commit/tree as the certified runtime identity unless they are actually byte/tree identical and proven so.

## Handoff requirement

Every future Yggdrasil handoff/continuation bundle must explicitly state this engineering method and the role separation:

1. GitHub = primary engineering/CI carrier and long-running execution environment.
2. Google Drive = byte-exact release/archive backup.
3. Hetzner = canonical live Yggdrasil substrate for deployment/live verification only.
4. Local execution = short exploratory/bounded work, not the preferred long-certification runner.

Every handoff should also restate the current source/package identities, certification status, live-state status, authority boundaries, backup locations, and the next permissible engineering action.

## Default rule

Unless a later explicit owner instruction changes this policy, future Yggdrasil engineering should follow this method by default.
