from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_intent(text: str):
    files = []
    current = None
    block = None
    for raw in text.splitlines():
        if raw.startswith("--- a/"):
            if current is not None and block is not None:
                current["blocks"].append(block)
            block = None
            current = {"path": raw[6:], "blocks": []}
            files.append(current)
            continue
        if raw.startswith("+++ b/"):
            continue
        if raw == "@@":
            if current is None:
                raise ValueError("intent hunk before file header")
            if block is not None:
                current["blocks"].append(block)
            block = []
            continue
        if block is not None:
            block.append(raw)
    if current is not None and block is not None:
        current["blocks"].append(block)
    return files


def block_text(lines):
    old, new = [], []
    for line in lines:
        if line.startswith("\\ No newline"):
            continue
        if not line:
            raise ValueError("bare empty line inside intent block; diff lines must carry a prefix")
        prefix, payload = line[0], line[1:]
        if prefix in (" ", "-"):
            old.append(payload)
        if prefix in (" ", "+"):
            new.append(payload)
        if prefix not in (" ", "-", "+"):
            raise ValueError(f"unexpected intent line prefix: {line!r}")
    def render(rows):
        return "".join(row + "\n" for row in rows)
    return render(old), render(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--intent", required=True)
    ap.add_argument("--audit", required=True)
    args = ap.parse_args()

    root = Path(args.root)
    sections = parse_intent(Path(args.intent).read_text(encoding="utf-8"))
    audit = []

    for section in sections:
        path = root / section["path"]
        data = path.read_text(encoding="utf-8")
        cursor = 0
        file_audit = {"path": section["path"], "blocks": []}

        for index, raw_block in enumerate(section["blocks"], start=1):
            old, new = block_text(raw_block)
            entry = {
                "index": index,
                "old_len": len(old),
                "new_len": len(new),
                "changed": old != new,
            }

            if not old and not new:
                entry["status"] = "empty-marker"
                file_audit["blocks"].append(entry)
                continue
            if not old:
                raise SystemExit(f"FAIL {section['path']} block {index}: insertion lacks an exact old-side anchor")

            pos = data.find(old, cursor)
            if pos < 0:
                raise SystemExit(
                    f"FAIL {section['path']} block {index}: old-side anchor not found after cursor {cursor}"
                )

            if old != new:
                second = data.find(old, pos + 1)
                if second >= 0:
                    raise SystemExit(
                        f"FAIL {section['path']} block {index}: ambiguous old-side anchor at {pos} and {second}"
                    )
                data = data[:pos] + new + data[pos + len(old):]
                cursor = pos + len(new)
                entry["status"] = "replaced-exactly-once"
            else:
                cursor = pos + len(old)
                entry["status"] = "context-anchor"

            entry["offset"] = pos
            file_audit["blocks"].append(entry)

        path.write_text(data, encoding="utf-8", newline="\n")
        audit.append(file_audit)

    result = {
        "status": "PASS",
        "authority": {
            "semantic_truth": False,
            "answer": False,
            "speech_act": False,
            "candidate_ranking": False,
            "cognitive_memory": False,
            "relationship": False,
            "source_write_runtime": False,
            "deployment": False,
        },
        "files": audit,
    }
    Path(args.audit).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
