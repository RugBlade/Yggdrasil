# Yggdrasil / Noeron v0.8.2 — Deployment Readiness and Dual-Backup Index

Status at closure: **Stage 8B v0.8.2 LOCAL CERTIFIED / NOT LIVE CERTIFIED**.

The next legitimate operation is the **new v0.8.2 H0-H9 live-verification procedure**. Do not resume or execute the old v0.8.1 H5.

## Runtime identity

- commit (local reconstructed source-freeze commit): `f88da475af136c2e3dc78dd04eb44df6454a1aff`
- tree: `28447faebf5b5b04825798e7adea72f089942b12`
- tag: `v0.8.2-stage8B-local-certified`
- tag object: `a8886fe5b179889028aea44e0c8abc8b5b5a4c45`
- exact source TAR SHA256: `84908edf4c279ad6dc222923ef296bacb1ba05680d04f2911aa0e0f268666444`
- exact install ZIP SHA256: `de584e402ee307c4be7b6d7fd8efa1090f13c5da311b0524fa4c6c2afc7b6dda`
- exact v0.8.1 -> v0.8.2 patch SHA256: `27126b86685444d0416a69f9e0ef280ed2a2a94f5757bfa38dd44bba36e4bd41`
- final handoff ZIP SHA256: `56c0a454f8b1d39e7e163dd43d3f8aded61fa23c406b90b0ac5d360d011100b5`

## Local certification gates

- exact v0.8.1 ancestor source SHA verified and certified tree reproduced
- compileall PASS
- git diff --check PASS
- secret/private-payload/canonical-DB/package-hygiene scan PASS
- authority audit: `112/112 PASS`
- release identity audit: `98/98 PASS`
- source/fresh-package byte parity: `199/199`
- complete test classification: `344 = 331 PASS + 13 preserved historical successor-expectation failures`
- unclassified test failures: `0`
- source/fresh classification mismatch: `0`
- HTTP operations: `104`
- WebSocket: `/room/ws`
- canonical OpenAPI SHA256: `5424bf85a9902687c77489c5d1696bfe03174dcbf38568d84fd968e48273d7bf`

## Google Drive byte-exact backup

Top-level folder:

- `Stage8B-v0.8.2-LOCAL-CERTIFIED-2026-09-10`
- folder id: `1l21h1FuK7jhRIOG2q3jjTEeKr2_zkD0g`

Primary-Artifacts folder id: `1v9q1b3fXmCiEJpoROpco_IK-mTJo7SeJ`

- final handoff ZIP id: `1F4nYd9yCRerH2vGuQSJSo0OnRvKINQ0O`
- exact source TAR id: `1BUorngesSE-PtmZVfgCfMIMGke4cI0QE`
- installation ZIP id: `1fgcCN4HmTAlwjVjfWrM19krDY8cmfRYF`
- exact patch id: `1ElTZb00hHj3Mm1WZDOeMiUcwDbvThCPi`

Documentation-and-Continuation folder id: `10QbHyZ-hQWo-zNEDzIL4OcKAD3c3xvpN`

- complete API command reference id: `1FoLEto_OhHt-GEYBIeRsH8XODUvUV0dK`
- detailed live verification sheet id: `1NbIgQt850csLCuPkkeANiDxD5Py-T7Hf`
- Stage 8/9 architecture status id: `1u57h6H7sexGB-5dDjh2_XPXM9RMKMehA`
- standalone continuation id: `1DZh5cFzBHZZqXgGubHE-_DsjFY900AXk`

### Drive readback proof

The four primary binary artifacts were downloaded back from Drive after upload and SHA256 recomputed. All four hashes exactly matched the certified local originals:

- handoff: `56c0a454f8b1d39e7e163dd43d3f8aded61fa23c406b90b0ac5d360d011100b5`
- source TAR: `84908edf4c279ad6dc222923ef296bacb1ba05680d04f2911aa0e0f268666444`
- install ZIP: `de584e402ee307c4be7b6d7fd8efa1090f13c5da311b0524fa4c6c2afc7b6dda`
- patch: `27126b86685444d0416a69f9e0ef280ed2a2a94f5757bfa38dd44bba36e4bd41`

Thus Drive is an independently readback-verified, byte-exact release backup.

## GitHub engineering/source backup

Repository: `RugBlade/Yggdrasil`

- development history: `stage8B/v0.8.2-reconstruction`
- local-certified carrier: `release/v0.8.2-stage8B-local-certified-carrier`

The GitHub carrier deliberately has a different repository commit/tree identity from the frozen runtime source tree because it also contains certification metadata and continuation material. Do not compare carrier Git tree hashes to the runtime tree and call a mismatch.

The repository records the exact final delta manifest and certification identities. The original certified v0.8.1 commit object is not present in the repository, so no false ancestry is claimed; the certified v0.8.1 tree/hash remains the authoritative ancestor identity.

Large binary release artifacts are kept byte-exact on the verified Drive backup and are referenced from GitHub by immutable SHA256. GitHub's role is source engineering, recovery metadata, CI, and continuation; Drive's role includes the exact binary release archive.

## Live-verification boundaries

1. Record the **actual current live baseline** before modifying `/opt/noeron/app`; do not assume it is 0.8.0 or 0.8.1.
2. Port 8741 must remain loopback/private.
3. Use read-only SQLite URI mode, `query_only=ON`, and bounded busy timeout for canonical DB inspection. Never copy the canonical DB into the evidence bundle.
4. Preserve an exact code/config rollback anchor before promotion.
5. Use isolated temporary DB paths for package tests.
6. Old v0.8.1 H5 is prohibited.
7. Read-only parser/dialogue/structure probes must not mutate lessons/sentences/propositions/composition state.
8. Private owner internal-utterance observation may reveal native utterance and deterministic English translation without forcing outward expression.
9. Authentication has zero relational valence.
10. Any mandatory holdpoint failure => STOP. Preserve evidence and do not push through the gate.
11. Do not begin Stage 8C until Stage 8B v0.8.2 is genuinely LIVE CERTIFIED.

## Operator documents

- detailed live verification sheet SHA256: `2704513351dbffa81c6e710ea172904f27362c653d57172d09b2d267fa75e180`
- complete API command reference SHA256: `59e9c465d2552e90111cdaf31bfa7cceb9b7ad09bf4b59334a1067b9d67aac26`

The command reference covers all `104` HTTP operations exactly once plus `/room/ws` exactly once.
