from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These hashes are taken from the exact v0.8.1 certified source TAR
# (SHA256 21e5d4a6883ce687cfe04e75c10b76a3d642d15567900f567c366399d36a5338).
FROZEN_V081_AUDIT_SHA256 = {
    "scripts/audit_v081_stage8B_language.py": "fd44555aadd9cfd2df6741c73b418e310a629bdaa2be21c41f1862e6b172b054",
    "scripts/audit_v081_stage8B_release_identity.py": "afc912941d7dd38ea07004c0338ab64c7a8784a110f8fa2a6f754ba73c2998b5",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_01_frozen_v081_audits_are_byte_preserved_from_certified_ancestor() -> None:
    """Successor source must not rewrite historical audits merely to make them green."""
    observed = {rel: _sha256(ROOT / rel) for rel in FROZEN_V081_AUDIT_SHA256}
    assert observed == FROZEN_V081_AUDIT_SHA256
