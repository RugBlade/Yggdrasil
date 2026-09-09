# Yggdrasil / Noeron engineering carrier

This repository is an engineering carrier for Noeron/Yggdrasil development, CI, source review, and certification documentation.

## Certification boundary

This GitHub repository commit history is **not** automatically the certified runtime identity. Repository-only files such as CI workflows, documentation, evidence indexes, and development branches may exist here without changing a frozen runtime source tree.

Current durable ancestor for revised Stage 8B reconstruction:

- Stage 8B v0.8.1 LOCAL CERTIFIED source TAR SHA-256: `21e5d4a6883ce687cfe04e75c10b76a3d642d15567900f567c366399d36a5338`
- Certified runtime commit: `a69b37876302605e71d96145a555a977e0b219bd`
- Certified runtime tree: `a1e4436c34edd87fe5592294de21382297d17ad3`
- Tag: `v0.8.1-stage8B-local-certified`

Revised Stage 8B v0.8.2 remains **IN PROGRESS / NOT LOCAL CERTIFIED / NOT LIVE DEPLOYED** until all source, package, fresh-extract, regression, authority, security, and evidence gates close.

## Security boundary

Never commit the canonical live Yggdrasil SQLite DB/state, `.env`, SSH/private keys, owner/device tokens, server credentials, unsanitized camera/microphone material, or private owner conversation exports.
