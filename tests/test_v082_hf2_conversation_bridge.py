from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from noeron.conversation_bridge import (
    HF2_CONVERSATION_BRIDGE_VERSION,
    NATIVE_REASONING_PATH,
    admit_live_current_turn,
    current_turn_interpretation,
    native_trace_from_math_state,
    proposition_envelopes,
)
from noeron.conversation_premises import (
    BoundedConversationalPremiseContext,
    CurrentTurnAudit,
    NativeGeometryTrace,
)


@dataclass
class P:
    subject: str
    relation: str
    object: str
    polarity: bool = True
    confidence: float = 1.0
    modifiers: list[str] = field(default_factory=list)

    def canonical(self) -> str:
        core = f"{self.subject}::{self.relation}::{self.object}"
        return core if self.polarity else f"not {core}"


def test_envelope_conversion_is_generic_and_zero_authority():
    envs = proposition_envelopes([P("mira", "opened", "door")], turn=4)
    assert len(envs) == 1
    e = envs[0]
    assert e.canonical == "mira::opened::door"
    assert e.source_turn == 4
    assert e.origin == "current-turn"
    assert e.authority.semantic_truth is False
    assert e.authority.cognitive_memory is False
    assert e.authority.answer is False


def test_correction_modifier_survives_bridge_and_supersedes_only_bounded_layer():
    ctx = BoundedConversationalPremiseContext(max_turns=8)
    admit_live_current_turn(
        ctx,
        turn=1,
        input_text="The box is red.",
        propositions=[P("box", "color", "red")],
    )
    r = admit_live_current_turn(
        ctx,
        turn=2,
        input_text="Correction: the box is blue.",
        propositions=[P("box", "color", "blue", modifiers=["correction"])],
    )
    rows = {p.object: p for p in ctx.premises}
    assert rows["red"].status == "superseded"
    assert rows["blue"].status == "active"
    assert rows["red"].canonical in rows["blue"].supersedes
    assert r.authority_audit["bounded_dialogue_is_cognitive_memory"] is False


def test_competing_values_without_correction_remain_explicit_conflict():
    ctx = BoundedConversationalPremiseContext()
    admit_live_current_turn(
        ctx,
        turn=1,
        input_text="The box is red.",
        propositions=[P("box", "color", "red")],
    )
    r = admit_live_current_turn(
        ctx,
        turn=2,
        input_text="The box is blue.",
        propositions=[P("box", "color", "blue")],
    )
    assert {p.status for p in r.eligible_premises} == {"conflict"}
    assert {p.object for p in r.eligible_premises} == {"red", "blue"}


def test_current_turn_interpretation_is_bound_to_exact_input_bytes():
    text = "Mira opened the door."
    audit = CurrentTurnAudit.from_input(
        turn=7,
        input_text=text,
        premise_canonicals=["mira::opened::door"],
    )
    out = current_turn_interpretation(
        audit=audit,
        turn=7,
        input_text=text,
        structure={"ambiguities": []},
    )
    assert out["version"] == HF2_CONVERSATION_BRIDGE_VERSION
    assert out["input_text"] == text
    assert out["freshness"] == "current-turn-exact-input-sha256"
    assert out["authority"]["answer"] is False
    with pytest.raises(RuntimeError, match="stale current-turn"):
        current_turn_interpretation(
            audit=audit,
            turn=7,
            input_text="Different turn text.",
            structure={},
        )


def test_dialogue_structure_counts_are_current_turn_only():
    ctx = BoundedConversationalPremiseContext()
    r = admit_live_current_turn(
        ctx,
        turn=3,
        input_text="Mira told Sara that she won. Who won?",
        propositions=[P("mira", "told", "sara")],
        structure={
            "ambiguities": [{"kind": "reference"}, {"kind": "event-role"}],
            "lexical_gaps": [{"surface": "foobar"}],
        },
    )
    assert r.audit.ambiguity_count == 2
    assert r.audit.lexical_gap_count == 1
    assert r.language_interpretation["ambiguity_count"] == 2
    assert r.language_interpretation["lexical_gap_count"] == 1


def test_pre_migration_history_cannot_be_replayed_through_live_bridge():
    ctx = BoundedConversationalPremiseContext()
    with pytest.raises(ValueError, match="historical/pre-migration"):
        admit_live_current_turn(
            ctx,
            turn=10,
            input_text="Old historical turn.",
            propositions=[P("old", "is", "historical")],
            prospective_floor_turn=10,
        )
    assert ctx.premises == []
    assert ctx.current_audit is None


def test_native_geometry_trace_is_carried_but_not_promoted_to_truth():
    trace = NativeGeometryTrace(
        irg_event_ids=("irg-1",),
        dkt_activation_ids=("dkt-1",),
        egr_region_ids=("egr-1",),
        rl_proof_ids=("rl-1",),
        frenet_trace_ids=("fr-1",),
    )
    ctx = BoundedConversationalPremiseContext()
    r = admit_live_current_turn(
        ctx,
        turn=1,
        input_text="Mira opened the door.",
        propositions=[P("mira", "opened", "door")],
        native_trace=trace,
    )
    e = r.eligible_premises[0]
    assert e.native_trace.has_native_trace is True
    assert e.native_trace.rl_proof_ids == ("rl-1",)
    assert e.authority.semantic_truth is False
    assert r.authority_audit["native_geometry_is_evidence_not_truth"] is True
    assert r.language_interpretation["native_reasoning_path"] == NATIVE_REASONING_PATH


def test_native_trace_is_extracted_from_existing_math_outputs_without_rerunning_math():
    math_state = SimpleNamespace(
        dkt=SimpleNamespace(retrieved_memory_ids=["mem-a", "mem-b"], invariant_signature="sig"),
        egr=SimpleNamespace(simultaneous_active_regions=["region:alpha", "region:beta"], dominant_activation_region="region:alpha"),
        reasoning=SimpleNamespace(
            inference_steps=[
                SimpleNamespace(rule="modus-ponens", premises=["a", "a->b"], conclusion="b", confidence=0.9)
            ]
        ),
        frenet=SimpleNamespace(samples=3, speed=1.25, first_curvature=0.5, metric_feedback_strength=0.2, tangent=[1, 0, 0]),
    )
    trace = native_trace_from_math_state(math_state, event_id="evt-7")
    assert trace.irg_event_ids == ("event:evt-7",)
    assert trace.dkt_activation_ids == ("mem-a", "mem-b")
    assert trace.egr_region_ids == ("region:alpha", "region:beta")
    assert len(trace.rl_proof_ids) == 1
    assert trace.rl_proof_ids[0].startswith("rl-proof:")
    assert len(trace.frenet_trace_ids) == 1
    assert trace.frenet_trace_ids[0].startswith("frenet:")


def test_native_trace_falls_back_to_actual_dkt_signature_only_when_no_memory_ids():
    math_state = {
        "dkt": {"retrieved_memory_ids": [], "invariant_signature": "knot-sig-9"},
        "egr": {"simultaneous_active_regions": [], "dominant_activation_region": ""},
        "reasoning": {"inference_steps": []},
        "frenet": {"samples": 0},
    }
    trace = native_trace_from_math_state(math_state)
    assert trace.dkt_activation_ids == ("dkt-knot:knot-sig-9",)
    assert trace.egr_region_ids == ()
    assert trace.rl_proof_ids == ()
    assert trace.frenet_trace_ids == ()


def test_empty_nonproposition_rows_are_not_promoted():
    ctx = BoundedConversationalPremiseContext()
    r = admit_live_current_turn(
        ctx,
        turn=1,
        input_text="What do you know?",
        propositions=[{"subject": "", "relation": "", "object": ""}],
        structure={"ambiguities": [], "lexical_gaps": []},
    )
    assert r.audit.premise_canonicals == ()
    assert r.eligible_premises == ()


def test_bounded_expiry_is_preserved_through_bridge():
    ctx = BoundedConversationalPremiseContext(max_turns=2)
    admit_live_current_turn(ctx, turn=1, input_text="A is one.", propositions=[P("a", "is", "one")])
    admit_live_current_turn(ctx, turn=2, input_text="B is two.", propositions=[P("b", "is", "two")])
    r = admit_live_current_turn(ctx, turn=3, input_text="C is three.", propositions=[P("c", "is", "three")])
    first = next(p for p in ctx.premises if p.subject == "a")
    assert first.status == "expired"
    assert {p.subject for p in r.eligible_premises} == {"b", "c"}


def test_bridge_exposes_no_historical_import_or_answer_authority():
    ctx = BoundedConversationalPremiseContext()
    r = admit_live_current_turn(ctx, turn=1, input_text="A is B.", propositions=[P("a", "is", "b")])
    assert r.authority_audit["historical_replay_api_present"] is False
    assert r.authority_audit["native_reasoning_required_for_answer_selection"] is True
    assert r.language_interpretation["authority"] == {
        "semantic_truth": False,
        "cognitive_memory": False,
        "answer": False,
        "speech_act": False,
        "relationship": False,
        "source_write": False,
        "deployment": False,
    }
