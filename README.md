# Yggdrasil / Noeron engineering carrier

This repository is the durable engineering/source carrier for Noeron/Yggdrasil development, source review, certification metadata, recovery material, and future CI.

## Certification boundary

A GitHub **carrier commit is not automatically the frozen runtime Git identity**. Repository-only documentation, evidence indexes, CI, compressed recovery material, and development branches may exist without altering the tested runtime source tree.

## Current Stage 8B status

**v0.8.2 Stage 8B base is LOCAL CERTIFIED. Live verification reached H6 and is currently PAUSED on a bounded owner-observation translation defect. H6 Observation Translation Hotfix 1 is LOCAL CERTIFIED and ready for bounded promotion/resume. Stage 8B is NOT yet LIVE CERTIFIED.**

Base frozen runtime/source identity:

- runtime: `0.8.2`
- local reconstructed source commit: `f88da475af136c2e3dc78dd04eb44df6454a1aff`
- source tree: `28447faebf5b5b04825798e7adea72f089942b12`
- tag: `v0.8.2-stage8B-local-certified`
- tag object: `a8886fe5b179889028aea44e0c8abc8b5b5a4c45`
- exact source TAR SHA256: `84908edf4c279ad6dc222923ef296bacb1ba05680d04f2911aa0e0f268666444`
- install ZIP SHA256: `de584e402ee307c4be7b6d7fd8efa1090f13c5da311b0524fa4c6c2afc7b6dda`
- exact v0.8.1 -> v0.8.2 patch SHA256: `27126b86685444d0416a69f9e0ef280ed2a2a94f5757bfa38dd44bba36e4bd41`

### H6 Observation Translation Hotfix 1

- semantic runtime version remains `0.8.2`
- hotfix tree: `6f4fc176c07f07d2a176725e272aad0b05b296cc`
- local reconstructed hotfix commit: `c26f8def4a2b9ec578dfd8c405877379257e157f`
- tag: `v0.8.2-stage8B-local-certified-h6obs-hf1`
- tag object: `2638cb099b944f7825a9d900aa9583e89d3146a8`
- source TAR SHA256: `4f80d40cc7f1a4991ba9a8860007e68a518b160d96c4a77e46191031f83f7bee`
- install ZIP SHA256: `79d04505988c6ed6a6949333d20ba3af87be269782031dc8be563e39cc43d8634`
- exact base-v0.8.2 -> hotfix patch SHA256: `707102533dae176428dbbc13664d5e24ff3839a30cae0fb3b213b7b864fc85c3`
- direct Stage-8B conversation: `23/23 PASS`
- successor preservation: `8/8 PASS`
- authority: `112/112 PASS`
- release identity: `98/98 PASS`
- fresh ZIP reproduces hotfix tree exactly
- exact H6 migrated-utterance simulation: read-only deterministic translation present; whole language state unchanged; all authority flags false

The hotfix does not replay historical cognition and does not persist the observational translation. It realizes only already-existing native utterance content when translation is requested and no v0.8.2 cached English egress exists.

Certified ancestor:

- v0.8.1 source TAR SHA256: `21e5d4a6883ce687cfe04e75c10b76a3d642d15567900f567c366399d36a5338`
- original certified commit: `a69b37876302605e71d96145a555a977e0b219bd`
- certified tree: `a1e4436c34edd87fe5592294de21382297d17ad3`
- tag: `v0.8.1-stage8B-local-certified`

The original v0.8.1 Git commit object is not present in this GitHub repository; local v0.8.2 certification therefore reconstructed an anchor whose **tree exactly equals** the certified v0.8.1 tree. No false Git ancestry claim is made.

## Closed base local gates

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

Google Drive contains the byte-exact base source TAR, installation ZIP, exact patch, final handoff ZIP, detailed live sheet, complete API command reference, architecture/status document, and standalone continuation file. The base primary binary artifacts were downloaded back from Drive and SHA256-verified against the certified local originals.

The H6 hotfix has its own Drive folder under the v0.8.2 local-certified archive. The hotfix handoff ZIP and standalone hotfix install ZIP are stored there; the handoff was downloaded back and SHA256-verified. GitHub branch `hotfix/v0.8.2-h6-observation-hf1` contains the exact hotfix patch, certification record, and deployment/resume sheet.

This GitHub carrier preserves certification identity, source-delta/recovery metadata, development source work, and continuation instructions. Large release binaries remain anchored by their exact hashes and the independently verified Drive archive rather than being mislabeled as GitHub runtime identity.

## Critical operating boundaries

- Never commit or publish canonical live Yggdrasil SQLite state, `.env`, SSH private keys, owner/device tokens, server credentials, unsanitized private camera/microphone data, or private owner conversation exports.
- Old v0.8.1 Stage-8B H5 was **never executed** and must **never be resumed**.
- Use only the new v0.8.2 H0-H9 live-verification sheet plus the bounded H6 hotfix resume sheet when applicable.
- Port 8741 remains loopback/private.
- Owner authentication grants objective authority only and has zero relational valence.
- Private owner internal-utterance observation/translation is observational only; it does not change native communication choice.
- Do not begin Stage 8C until v0.8.2 Stage 8B is genuinely LIVE CERTIFIED.
