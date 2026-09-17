"""HF2 current-turn bridge from transparent language logic into bounded dialogue premises.

This module is intentionally narrow. It converts already-parsed proposition objects
into provenance envelopes, advances only the supplied *live current turn*, and emits
a fresh interpretation/audit object keyed to the exact input bytes.

It does NOT replay history, create cognitive memory, assert truth, choose an answer,
select a speech act, write source, deploy code, or infer relationship meaning.
Native answer selection remains downstream of the canonical machinery:
IRG -> DKT -> regional EGR -> RL/Frenet -> DKT -> native cognition/action.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

from noeron.conversation_premises import (
    BoundedConversationalPremiseContext,
    ConversationalPremiseEnvelope,
    CurrentTurnAudit,
    NativeGeometryTrace,
)

HF2_CONVERSATION_BRIDGE_VERSION = "0.8.2-stage8B-hf2-current-turn-bridge-v1"
NATIVE_REASONING_PATH = "IRG->DKT->regional-EGR->RL/Frenet->DKT->native-cognition/action"


def _field(row: object, name: str, default: Any = "") -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _canonical(row: object) -> str:
    fn = getattr(row, "canonical", None)
    if callable(fn):
        value = str(fn() or "").strip()
        if value:
            return value
    explicit = str(_field(row, "canonical", "") or "").strip()
    if explicit:
        return explicit
    subject = str(_field(row, "subject", "") or "").strip()
    relation = str(_field(row, "relation", "") or "").strip()
    obj = str(_field(row, "object", "") or "").strip()
    polarity = bool(_field(row, "polarity", True))
    if not subject or not relation:
        return ""
    core = f"{subject}::{relation}::{obj}"
    return core if polarity else f"not {core}"


def _modifiers(row: object) -> tuple[str, ...]:
    raw = _field(row, "modifiers", ()) or ()
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(x) for x in raw)


def _seq(row: object, name: str) -> tuple[object, ...]:
    raw = _field(row, name, ()) or ()
    if isinstance(raw, (str, bytes)):
        return (raw,)
    try:
        return tuple(raw)
    except TypeError:
        return ()


def _proof_ref(step: object) -> str:
    payload = {
        "rule": str(_field(step, "rule", "") or ""),
        "premises": [str(x) for x in _seq(step, "premises")],
        "conclusion": str(_field(step, "conclusion", "") or ""),
        "confidence": float(_field(step, "confidence", 0.0) or 0.0),
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"rl-proof:{digest}"


def native_trace_from_math_state(math_state: object, *, event_id: str = "") -> NativeGeometryTrace:
    """Create evidence references from an already-computed native math state.

    This helper never re-runs or replaces IRG/DKT/EGR/RL/Frenet. It records stable
    references to outputs that already exist after that machinery has run. Presence
    of a reference is *not* semantic truth or answer authority.
    """
    dkt = _field(math_state, "dkt", None)
    egr = _field(math_state, "egr", None)
    reasoning = _field(math_state, "reasoning", None)
    frenet = _field(math_state, "frenet", None)

    irg_ids = (f"event:{event_id}",) if str(event_id).strip() else ()

    dkt_ids = tuple(str(x) for x in _seq(dkt, "retrieved_memory_ids") if str(x).strip())
    if not dkt_ids:
        signature = str(_field(dkt, "invariant_signature", "") or "").strip()
        if signature and signature != "uninitialized":
            dkt_ids = (f"dkt-knot:{signature}",)

    egr_ids = tuple(str(x) for x in _seq(egr, "simultaneous_active_regions") if str(x).strip())
    if not egr_ids:
        dominant = str(_field(egr, "dominant_activation_region", "") or "").strip()
        if dominant:
            egr_ids = (dominant,)

    rl_ids = tuple(_proof_ref(step) for step in _seq(reasoning, "inference_steps"))

    frenet_ids: tuple[str, ...] = ()
    samples = int(_field(frenet, "samples", 0) or 0)
    if samples > 0:
        payload = {
            "samples": samples,
            "speed": float(_field(frenet, "speed", 0.0) or 0.0),
            "first_curvature": float(_field(frenet, "first_curvature", 0.0) or 0.0),
            "metric_feedback_strength": float(_field(frenet, "metric_feedback_strength", 0.0) or 0.0),
            "tangent": [float(x) for x in _seq(frenet, "tangent")],
        }
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        frenet_ids = (f"frenet:{digest}",)

    return NativeGeometryTrace(
        irg_event_ids=irg_ids,
        dkt_activation_ids=dkt_ids,
        egr_region_ids=egr_ids,
        rl_proof_ids=rl_ids,
        frenet_trace_ids=frenet_ids,
    )


def proposition_envelopes(
    propositions: Iterable[object],
    *,
    turn: int,
    native_trace: NativeGeometryTrace | None = None,
) -> tuple[ConversationalPremiseEnvelope, ...]:
    """Convert parser/inference proposition objects into zero-authority envelopes.

    The bridge accepts attribute objects or mappings so the current HF1 proposition
    model can be wired without teaching this module any sentence-specific semantics.
    Empty/non-propositional rows are ignored rather than promoted to premises.
    """
    trace = native_trace or NativeGeometryTrace()
    out: list[ConversationalPremiseEnvelope] = []
    for row in propositions:
        subject = str(_field(row, "subject", "") or "").strip()
        relation = str(_field(row, "relation", "") or "").strip()
        obj = str(_field(row, "object", "") or "").strip()
        canonical = _canonical(row)
        if not canonical or not subject or not relation:
            continue
        out.append(
            ConversationalPremiseEnvelope(
                canonical=canonical,
                subject=subject,
                relation=relation,
                object=obj,
                polarity=bool(_field(row, "polarity", True)),
                source_turn=int(turn),
                origin="current-turn",
                correction="correction" in _modifiers(row),
                confidence=float(_field(row, "confidence", 1.0) or 1.0),
                native_trace=trace,
            )
        )
    return tuple(out)


def _structure_counts(structure: Mapping[str, object] | None) -> tuple[int, int]:
    s = structure or {}
    return len(list(s.get("ambiguities") or [])), len(list(s.get("lexical_gaps") or []))


def current_turn_interpretation(
    *,
    audit: CurrentTurnAudit,
    turn: int,
    input_text: str,
    structure: Mapping[str, object] | None,
) -> dict[str, object]:
    """Build a current-turn-only interpretation and reject stale audit reuse."""
    if not audit.matches(turn=int(turn), input_text=input_text):
        raise RuntimeError("stale current-turn interpretation/audit")
    return {
        "version": HF2_CONVERSATION_BRIDGE_VERSION,
        "turn": int(turn),
        "input_text": input_text,
        "input_sha256": sha256(input_text.encode("utf-8")).hexdigest(),
        "premise_canonicals": list(audit.premise_canonicals),
        "ambiguity_count": int(audit.ambiguity_count),
        "lexical_gap_count": int(audit.lexical_gap_count),
        "structure": dict(structure or {}),
        "freshness": "current-turn-exact-input-sha256",
        "native_reasoning_path": NATIVE_REASONING_PATH,
        "authority": {
            "semantic_truth": False,
            "cognitive_memory": False,
            "answer": False,
            "speech_act": False,
            "relationship": False,
            "source_write": False,
            "deployment": False,
        },
    }


@dataclass(frozen=True)
class CurrentTurnBridgeResult:
    audit: CurrentTurnAudit
    language_interpretation: dict[str, object]
    eligible_premises: tuple[ConversationalPremiseEnvelope, ...]
    authority_audit: dict[str, object]


def admit_live_current_turn(
    context: BoundedConversationalPremiseContext,
    *,
    turn: int,
    input_text: str,
    propositions: Sequence[object],
    structure: Mapping[str, object] | None = None,
    native_trace: NativeGeometryTrace | None = None,
    prospective_floor_turn: int | None = None,
) -> CurrentTurnBridgeResult:
    """Admit exactly one live current turn into bounded non-memory context.

    ``prospective_floor_turn`` is the migration/start boundary. A caller may use it
    to prove that pre-migration historical turns are never replayed into HF2 working
    context. No API for bulk historical import exists here by design.
    """
    turn = int(turn)
    if turn < 0:
        raise ValueError("turn must be non-negative")
    if prospective_floor_turn is not None and turn <= int(prospective_floor_turn):
        raise ValueError("historical/pre-migration turn cannot be admitted prospectively")

    envelopes = proposition_envelopes(propositions, turn=turn, native_trace=native_trace)
    ambiguity_count, lexical_gap_count = _structure_counts(structure)
    audit = context.admit_turn(
        turn=turn,
        input_text=input_text,
        premises=envelopes,
        ambiguity_count=ambiguity_count,
        lexical_gap_count=lexical_gap_count,
    )
    interpretation = current_turn_interpretation(
        audit=audit,
        turn=turn,
        input_text=input_text,
        structure=structure,
    )
    eligible = context.eligible(include_conflicts=True)
    authority = dict(context.authority_audit())
    authority.update(
        {
            "bridge_version": HF2_CONVERSATION_BRIDGE_VERSION,
            "current_turn_audit_fresh": True,
            "historical_replay_api_present": False,
            "native_geometry_is_evidence_not_truth": True,
        }
    )
    return CurrentTurnBridgeResult(
        audit=audit,
        language_interpretation=interpretation,
        eligible_premises=eligible,
        authority_audit=authority,
    )
