from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

EXPECTED_ZIP_SHA256 = "79d04505988c6ed6a694e952d8fce4bd9265d1214a96baf490bb6280ecb08c29"
EXPECTED_FILES = {
    "src/noeron/inference.py": "16254342bb82fa03c4dfa19533c46b1e7c8e3d070a89ebb59a856f5448c352f8",
    "src/noeron/models.py": "58d6523d02da387b606fb4c11bbe659ddf59ad795cf6c9a5a1530a0e8fd81d09",
    "src/noeron/orchestrator.py": "f6b3b807e8db58342a5d8f3de6d9b1a1db6b348a8a964f830b4943c43ba8b23d",
    "src/noeron/api.py": "826f89750b09c80a33f04cf3be071d83d37105196f2d6c8bad5a50566c60dd31",
    "src/noeron/math/models.py": "cf78d34ce162f973fc8169031bc231c79914b804fa758ac434665b29f8854161",
    "src/noeron/reasoning.py": "cfffa5cc31fe4ad49a1a026bc5bc02b3707fb1469b8e38e83a23ebe7073d4aeb",
    "src/noeron/math/kernel.py": "81fd1747fcdcda530eca5671f92878c4cc65fea9448a32ba57207459a4bc6d08",
}
FORBIDDEN_SUFFIXES = (".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--zip",
        default="fixtures/hf1_exact/noeron_starter_v0.8.2_stage8B_h6obs_hf1.zip",
    )
    ap.add_argument("--extract-dir", default="")
    ap.add_argument("--evidence", default="")
    args = ap.parse_args()

    archive = Path(args.zip)
    if not archive.is_file():
        fail(f"missing fixture: {archive}")

    archive_bytes = archive.read_bytes()
    archive_sha = sha256_bytes(archive_bytes)
    if archive_sha != EXPECTED_ZIP_SHA256:
        fail(f"zip sha256 {archive_sha} != {EXPECTED_ZIP_SHA256}")

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            fail("duplicate ZIP member names")

        forbidden = []
        for name in names:
            low = name.lower()
            base = Path(low).name
            if base == ".env" or low.endswith(FORBIDDEN_SUFFIXES):
                forbidden.append(name)
        if forbidden:
            fail("forbidden sensitive payload names: " + ", ".join(forbidden))

        observed = {}
        extracted = Path(args.extract_dir) if args.extract_dir else None
        for path, expected in EXPECTED_FILES.items():
            if path not in names:
                fail(f"missing required HF1 member: {path}")
            data = zf.read(path)
            got = sha256_bytes(data)
            if got != expected:
                fail(f"{path} sha256 {got} != {expected}")
            observed[path] = {
                "sha256": got,
                "size_bytes": len(data),
                "crlf_count": data.count(b"\r\n"),
                "lf_count": data.count(b"\n"),
            }
            if extracted is not None:
                target = extracted / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

    evidence = {
        "gate": "HF2 exact HF1 fixture identity",
        "status": "PASS",
        "certification_claim": False,
        "live_runtime_touched": False,
        "canonical_db_touched": False,
        "archive": {
            "path": str(archive),
            "size_bytes": len(archive_bytes),
            "sha256": archive_sha,
            "member_count": len(names),
        },
        "verified_files": observed,
        "forbidden_payload_hits": [],
    }

    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        Path(args.evidence).write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")


if __name__ == "__main__":
    main()
