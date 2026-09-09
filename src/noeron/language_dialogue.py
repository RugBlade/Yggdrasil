from __future__ import annotations

"""Stage 8B v0.8.2 transparent productive conversation substrate.

This module supplies deterministic *linguistic candidates*: morphology, clause
structure, event/semantic-role candidates, reference alternatives, lexical gaps,
question-under-discussion metadata and speech-act affordances.  It never decides
truth, cognitive memory, relationship meaning, whether to speak, answer content,
Terra use, source mutation, deployment, or initiative.

All factual/native proposition authority remains upstream in the canonical
Environment -> IRG -> DKT -> regional EGR -> RL/Frenet -> DKT -> native cognition
path.  The dialogue state maintained here is bounded working context, not
cognitive memory.
"""

import hashlib
import re
from typing import Mapping, Iterable

from noeron.language_composition import analyze_surface_composition

CONVERSATION_VERSION = "0.8.2-stage8B-native-conversation-v1"
DIALOGUE_VERSION = "0.8.2-stage8B-dialogue-v1"
PRODUCTIVE_ENGLISH_VERSION = "0.8.2-stage8B-productive-english-v1"

_WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_PRONOUNS = {"i","me","you","he","him","she","her","it","we","us","they","them","this","that","these","those"}
_DEICTIC = {"this","that","these","those","here","there","now","earlier","later","today","yesterday","tomorrow"}
_AUX = {"am","is","are","was","were","be","been","being","do","does","did","have","has","had"}
_MODALS = {"can","could","may","might","will","would","should","must"}
_DETERMINERS = {"a","an","the","all","every","each","some","any","no"}
_CONJ = {"and","or","but","although","though","however","yet","whereas","because","if","then","before","after"}
_PREP = {"in","on","at","by","with","for","from","to","into","through","near","under","above","behind","beside","inside","before","after"}
_QUESTION = {"why","how","when","where","who","which","what"}
_FUNCTION = _PRONOUNS | _AUX | _MODALS | _DETERMINERS | _CONJ | _PREP | _QUESTION | {
    "not","never","nor","of","as","so","than","very","more","most","less","least","yes","no"
}

SPEECH_ACT_AFFORDANCES = (
    "assert","answer","ask","clarify","correct","contrast","explain",
    "hypothesize","acknowledge","defer","refuse","remain-silent",
)


def words(text: str) -> list[str]:
    return [x.lower() for x in _WORD_RE.findall(text)]


def lemma(word: str) -> str:
    """Small deterministic morphology normalizer; it has zero truth authority."""
    w = word.lower().strip()
    irregular = {
        "am":"be","is":"be","are":"be","was":"be","were":"be","been":"be","being":"be",
        "has":"have","had":"have","does":"do","did":"do","went":"go","gone":"go",
    }
    if w in irregular:
        return irregular[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("ing"):
        base = w[:-3]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    # Past-tense -ed forms are preserved rather than guessed: a transparent
    # grammar may identify tense without pretending to know an irregular/base
    # lexical binding. Query forms introduced by did/does already expose a base
    # surface verb and can still be matched productively.
    if len(w) > 3 and w.endswith("ed"):
        return w
    if len(w) > 4 and w.endswith(("ches","shes","sses","xes","zes","oes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("es") and not w.endswith("sses"):
        return w[:-1]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _content_words(text: str) -> list[str]:
    return [w for w in words(text) if w not in _FUNCTION]


def _question_family(sentence: str) -> str:
    ws = words(sentence)
    if not ws:
        return ""
    if ws[0] in _QUESTION:
        return f"{ws[0]}-question"
    if (ws[0] in _AUX or ws[0] in _MODALS) and sentence.rstrip().endswith("?"):
        return "yes-no-question"
    return "open-question" if sentence.rstrip().endswith("?") else ""


def _event_candidates(sentence: str) -> list[dict]:
    """Return role candidates only; none of these rows asserts semantic truth."""
    s = sentence.strip().rstrip(".!?")
    low = s.lower()
    rows: list[dict] = []

    # Passive surface: "the book was placed by Mira".
    m = re.match(r"^(?:the\s+)?(.+?)\s+(?:was|were|is|are|been|be)\s+([a-z][a-z-]*ed)\s+by\s+(.+)$", low)
    if m:
        patient, verb, agent = m.groups()
        rows.append({
            "predicate_surface": verb, "predicate_lemma": lemma(verb),
            "voice": "passive-surface",
            "roles": {"agent": agent.strip(), "patient": patient.strip()},
            "authority": "candidate-only",
        })
        return rows

    # Ditransitive: "Mira gave Omar the book".
    m = re.match(r"^(.+?)\s+([a-z][a-z-]*)\s+(.+?)\s+(?:a\s+|an\s+|the\s+)?([^ ]+)$", low)
    if m:
        subj, verb, middle, final = m.groups()
        if verb not in _FUNCTION and len(words(middle)) <= 4:
            rows.append({
                "predicate_surface": verb, "predicate_lemma": lemma(verb), "voice": "active-surface",
                "roles": {"agent": subj.strip(), "recipient_or_theme": middle.strip(), "theme_or_patient": final.strip()},
                "ambiguity": "ditransitive-role-order-candidate",
                "authority": "candidate-only",
            })

    # Copular candidate.
    m = re.match(r"^(.+?)\s+(am|is|are|was|were)\s+(.+)$", low)
    if m:
        subj, cop, pred = m.groups()
        rows.append({
            "predicate_surface": cop, "predicate_lemma": "be", "voice": "copular-surface",
            "roles": {"theme": subj.strip(), "attribute_or_identity": pred.strip()},
            "authority": "candidate-only",
        })

    # Generic SVO candidate.
    m = re.match(r"^(.+?)\s+([a-z][a-z-]*)\s+(.+)$", low)
    if m:
        subj, verb, obj = m.groups()
        if verb not in _FUNCTION:
            role = {"agent": subj.strip(), "patient_or_theme": obj.strip()}
            # Detect transparent obliques without claiming attachment truth.
            pm = re.search(r"\b(with|in|on|at|by|from|to|near|under|above|behind|beside|inside)\b\s+(.+)$", obj)
            ambiguity = ""
            if pm:
                role["oblique_candidate"] = pm.group(2).strip()
                role["oblique_relation"] = pm.group(1)
                if pm.group(1) == "with":
                    ambiguity = "instrument-or-comitative-or-attachment"
            rows.append({
                "predicate_surface": verb, "predicate_lemma": lemma(verb), "voice": "active-surface",
                "roles": role, "ambiguity": ambiguity, "authority": "candidate-only",
            })
    return rows


def _reference_candidates(tokens: list[str], recent_referents: Iterable[Mapping[str, object]], legacy: Mapping[str, str]) -> tuple[list[dict], list[dict]]:
    recent = [dict(x) for x in recent_referents if isinstance(x, Mapping)]
    refs: list[dict] = []
    ambiguities: list[dict] = []
    for index, token in enumerate(tokens):
        if token not in _PRONOUNS and token not in _DEICTIC:
            continue
        candidates: list[str] = []
        if token in {"i","me"}:
            candidates = [str(legacy.get("speaker") or "speaker:self")]
        elif token == "you":
            candidates = [str(legacy.get("addressee") or "interlocutor:self")]
        elif token in {"it","this","that","these","those"}:
            candidates = [str(x.get("surface") or x.get("referent") or "") for x in reversed(recent) if x.get("kind") != "person"][:3]
            if not candidates:
                fallback = str(legacy.get("last_direct_object") or legacy.get("last_subject") or "")
                if fallback:
                    candidates = [fallback]
        elif token in {"he","him","she","her","they","them","we","us"}:
            candidates = [str(x.get("surface") or x.get("referent") or "") for x in reversed(recent) if x.get("kind") in {"person","unknown"}][:3]
            if not candidates and legacy.get("last_subject"):
                candidates = [str(legacy["last_subject"])]
        candidates = list(dict.fromkeys(x for x in candidates if x))
        status = "resolved-unique-candidate" if len(candidates) == 1 else ("ambiguous-alternatives-preserved" if len(candidates) > 1 else "unresolved-no-candidate")
        row = {"surface": token, "token_index": index, "candidates": candidates, "status": status, "authority": "grammatical-reference-candidate-only"}
        refs.append(row)
        if len(candidates) != 1:
            ambiguities.append({"kind": "reference", **row})
    return refs, ambiguities


def analyze_dialogue_structure(
    text: str,
    *,
    lexicon: Mapping[str, object] | None = None,
    recent_referents: Iterable[Mapping[str, object]] = (),
    legacy_context: Mapping[str, str] | None = None,
    speaker: str = "external:unknown",
    addressee: str = "interlocutor:self",
) -> dict:
    """Read-only productive structural analysis for a single ingress."""
    lexicon = lexicon or {}
    legacy = dict(legacy_context or {})
    legacy.setdefault("speaker", speaker)
    legacy.setdefault("addressee", addressee)
    toks = words(text)
    refs, ref_ambiguities = _reference_candidates(toks, recent_referents, legacy)
    sentences = [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]
    rows = []
    events = []
    for i, sentence in enumerate(sentences):
        ev = _event_candidates(sentence)
        events.extend({"sentence_index": i, **x} for x in ev)
        rows.append({
            "index": i,
            "text": sentence,
            "question_family": _question_family(sentence),
            "events": ev,
        })

    unknown = []
    for w in _content_words(text):
        lw = w.lower()
        root = lemma(lw)
        if lw not in lexicon and root not in lexicon:
            unknown.append({"surface": lw, "lemma_candidate": root, "status": "lexical-gap", "authority": "unknown-word-representation-only"})
    # Preserve unique unknown surfaces in first-seen order.
    seen = set(); unknown = [x for x in unknown if not (x["surface"] in seen or seen.add(x["surface"]))]

    ambiguities = list(ref_ambiguities)
    for e in events:
        if e.get("ambiguity"):
            ambiguities.append({"kind": "event-role", "sentence_index": e["sentence_index"], "alternatives": e["ambiguity"], "authority": "alternatives-preserved"})

    qfamilies = [x["question_family"] for x in rows if x["question_family"]]
    deictic = [{"surface": w, "status": "deictic-anchor-required" if w not in {"now"} else "current-turn-anchor", "authority": "context-candidate-only"} for w in toks if w in _DEICTIC]
    morphology = [{"surface": w, "lemma": lemma(w)} for w in toks]
    composition = analyze_surface_composition(text)
    return {
        "conversation_version": CONVERSATION_VERSION,
        "dialogue_version": DIALOGUE_VERSION,
        "productive_english_version": PRODUCTIVE_ENGLISH_VERSION,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "speaker": speaker,
        "addressee": addressee,
        "tokens": toks,
        "morphology": morphology,
        "sentences": rows,
        "event_candidates": events,
        "reference_candidates": refs,
        "deixis_candidates": deictic,
        "ambiguities": ambiguities,
        "lexical_gaps": unknown,
        "question_families": qfamilies,
        "speech_act_affordances": list(SPEECH_ACT_AFFORDANCES),
        "speech_act_selection_authority": False,
        "semantic_truth_authority": False,
        "answer_authority": False,
        "cognitive_memory_authority": False,
        "relationship_authority": False,
        "terra_authority": False,
        "source_write_authority": False,
        "deployment_authority": False,
        "initiative_authority": False,
        "composition": composition,
    }


def referent_mentions(analysis: Mapping[str, object]) -> list[dict]:
    """Extract bounded *surface* mention candidates for working dialogue state."""
    out: list[dict] = []
    for event in analysis.get("event_candidates", []) if isinstance(analysis, Mapping) else []:
        if not isinstance(event, Mapping):
            continue
        roles = event.get("roles") or {}
        if not isinstance(roles, Mapping):
            continue
        for role, surface in roles.items():
            if role in {"oblique_relation"}:
                continue
            s = str(surface or "").strip()
            if not s or "_or_" in role:
                # Ambiguous semantic roles still contribute a neutral mention.
                pass
            kind = "person" if role in {"agent","recipient"} else "unknown"
            if s:
                out.append({"surface": s, "role": role, "kind": kind})
    return out[-24:]
