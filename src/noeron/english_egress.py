from __future__ import annotations

"""Deterministic owner-readable English realization for Stage 8B v0.8.2.

The egress receives content that already exists in a native thought/utterance.
It may inflect and punctuate that content, but it cannot add propositions, select
truth, choose whether Yggdrasil communicates, invoke Terra, alter memory or
relationship state, write source, deploy code, or create initiative.
"""

import re
from typing import Iterable

from noeron.cognition.models import NativeProposition, NativeThought, NativeUtterance

ENGLISH_EGRESS_VERSION = "0.8.2-stage8B-english-egress-v1"


def _cap(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def _subject_agreement(subject: str, relation: str) -> str:
    r = relation.strip()
    low = r.lower()
    if low not in {"be", "is", "are", "am", "was", "were"}:
        return r
    s = subject.strip().lower()
    if low in {"was", "were"}:
        return "were" if s in {"you","we","they"} else "was"
    if s == "i":
        return "am"
    if s in {"you","we","they"}:
        return "are"
    return "is"


def realize_proposition(p: NativeProposition) -> str:
    subject = str(p.subject or "").strip()
    relation = str(p.relation or "").strip()
    obj = str(p.object or "").strip()
    if not subject or not relation:
        return ""
    relation = _subject_agreement(subject, relation)
    # Native proof internals sometimes encode predicate truth as object=true.
    # Removing that serialization marker from a non-copular predicate changes no
    # proposition; it prevents malformed surfaces such as "X failed true".
    if obj.lower() == "true" and relation.lower() not in {"is","are","am","was","were","is not","are not","was not","were not"}:
        core = f"{subject} {relation}"
    elif obj:
        core = f"{subject} {relation} {obj}"
    else:
        core = f"{subject} {relation}"
    core = _cap(core).rstrip(".!?")
    return core + "." if core else ""


def _question_surface(question: str) -> str:
    q = _cap(question).rstrip(".!?")
    return q + "?" if q else ""


def realize_native_thought(thought: NativeThought, utterance: NativeUtterance | None = None) -> tuple[str, dict]:
    """Return deterministic English plus a zero-authority audit."""
    sentences: list[str] = []
    source_units: list[str] = []
    for p in thought.propositions:
        rendered = realize_proposition(p)
        if rendered:
            sentences.append(rendered)
            source_units.append(f"proposition:{p.subject}|{p.relation}|{p.object}")
    for q in thought.question_candidates:
        rendered = _question_surface(q)
        if rendered:
            sentences.append(rendered)
            source_units.append(f"question:{q}")
    # If a native utterance has content but no structured proposition survived,
    # preserve it verbatim except deterministic whitespace/punctuation.  This is a
    # realization of existing content, not a generated fallback.
    if not sentences and utterance is not None and utterance.native_text.strip():
        raw = _cap(utterance.native_text)
        if raw and raw[-1] not in ".!?":
            raw += "."
        sentences.append(raw)
        source_units.append("native-utterance-existing-text")
    text = " ".join(x for x in sentences if x).strip()
    audit = {
        "version": ENGLISH_EGRESS_VERSION,
        "deterministic": True,
        "source_units": source_units,
        "source_proposition_count": len(thought.propositions),
        "source_question_count": len(thought.question_candidates),
        "english_text_present": bool(text),
        "semantic_truth_authority": False,
        "content_authority": False,
        "answer_authority": False,
        "speech_act_selection_authority": False,
        "cognitive_memory_authority": False,
        "relationship_authority": False,
        "terra_authority": False,
        "source_write_authority": False,
        "deployment_authority": False,
        "initiative_authority": False,
    }
    return text, audit
