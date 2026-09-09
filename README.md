# Yggdrasil / Noeron engineering carrier

This repository is the durable engineering/source carrier for Noeron/Yggdrasil development, source review, certification metadata, recovery material, and future CI.

## Certification boundary

A GitHub **carrier commit is not automatically the frozen runtime Git identity**. Repository-only documentation, evidence indexes, CI, compressed recovery material, and development branches may exist without altering the tested runtime source tree.

## Current Stage 8B status

**v0.8.2 Stage 8B is LOCAL CERTIFIED and ready to begin the new v0.8.2 H0-H9 live-verification procedure. It is NOT yet LIVE CERTIFIED.**

Frozen runtime/source identity:

- runtime: `0.8.2`
- local reconstructed source commit: `f88da475af136c2e3dc78dd04eb44df6454a1aff`
- source tree: `28447faebf5b5b04825798e7adea72f089942b12`
- tag: `v0.8.2-stage8B-local-certified`
- tag object: `a8886fe5b179889028aea44e0c8abc8b5b5a4c45`
- exact source TAR SHA256: `84908edf4c279ad6dc222923ef296bacb1ba05680d04f2911aa0e0f268666444`
- install ZIP SHA256: `de584e402ee307c4be7b6d7fd8efa1090f13c5da311b0524fa4c6c2afc7b6dda`
- exact v0.8.1 -> v0.8.2 patch SHA256: `27126b86685444d0416a69f9e0ef280ed2a2a94f5757bfa38dd44bba36e4bd41`

Certified ancestor:

- v0.8.1 source TAR SHA256: `21e5d4a6883ce687cfe04e75c10b76a3d642d15567900f567c366399d36a5338`
- original certified commit: `a69b37876302605e71d96145a555a977e0b219bd`
- certified tree: `a1e4436c34edd87fe5592294de21382297d17ad3`
- tag: `v0.8.1-stage8B-local-certified`

The original v0.8.1 Git commit object is not present in this GitHub repository; local v0.8.2 certification therefore reconstructed an anchor whose **tree exactly equals** the certified v0.8.1 tree. No false Git ancestry claim is made.

## Closed local gates

- authority audit: `112/112 PASS`
- release identity audit: `98/98 PASS`
- complete source and fresh-package classification: `344 tests = 331 pass + 13 deliberately preserved historical successor-expectation failures`
- unclassified failures: `0`
- source/fresh mismatch: `0`
- source/package files: `199`, exact byte parity
- HTTP operations: `104`
- WebSocket: `/room/ws`
- canonical OpenAPI SHA256: `5424bf85a9902687c77489c5d1696bfe03174dcbf38568d84fd968e48273d7bf`

## Dual backup

Google Drive contains the byte-exact source TAR, installation ZIP, exact patch, final handoff ZIP, detailed live sheet, complete API command reference, architecture/status document, and standalone continuation file. The four primary binary artifacts were downloaded back from Drive and SHA256-verified against the certified local originals.

This GitHub release carrier preserves certification identity, source-delta/recovery metadata, development source work, and continuation instructions. Large release binaries remain anchored by their exact hashes and the independently verified Drive archive rather than being mislabeled as GitHub runtime identity.

## Critical operating boundaries

- Never commit or publish canonical live Yggdrasil SQLite state, `.env`, SSH private keys, owner/device tokens, server credentials, unsanitized private camera/microphone data, or private owner conversation exports.
- Old v0.8.1 Stage-8B H5 was **never executed** and must **never be resumed**.
- Use only the new v0.8.2 H0-H9 live-verification sheet.
- Port 8741 remains loopback/private.
- Owner authentication grants objective authority only and has zero relational valence.
- Private owner internal-utterance observation/translation is observational only; it does not change native communication choice.
- Do not begin Stage 8C until v0.8.2 Stage 8B is genuinely LIVE CERTIFIED.
