from __future__ import annotations

import pytest

from noeron.conversation_premises import (
    BoundedConversationalPremiseContext,
    ConversationalPremiseEnvelope,
    CurrentTurnAudit,
    NativeGeometryTrace,
    PremiseAuthority,
)


def premise(
    canonical: str,
    *,
    subject: str,
    relation: str,
    object: str,
    turn: int,
    polarity: bool = True,
    correction: bool = False,
) -> ConversationalPremiseEnvelope:
    return ConversationalPremiseEnvelope(
        canonical=canonical,
        subject=subject,
        relation=relation,
        object=object,
        polarity=polarity,
        source_turn=turn,
        origin="current-turn",
        correction=correction,
    )


def test_bounded_dialogue_cannot_acquire_authority() -> None:
    with pytest.raises(ValueError, match="cannot acquire authority"):
        ConversationalPremiseEnvelope(
            canonical="box::is::blue",
            subject="box",
            relation="is",
            object="blue",
            polarity=True,
            source_turn=1,
            origin="current-turn",
            authority=PremiseAuthority(semantic_truth=True),
        )


def test_current_turn_audit_is_bound_to_turn_and_input_bytes() -> None:
    audit = CurrentTurnAudit.from_input(
        turn=7,
        input_text="The lamp is on.",
        premise_canonicals=["lamp::is::on"],
    )
    assert audit.matches(turn=7, input_text="The lamp is on.")
    assert not audit.matches(turn=8, input_text="The lamp is on.")
    assert not audit.matches(turn=7, input_text="The lamp is off.")


def test_context_promotes_current_turn_to_bounded_working_premise_without_memory_authority() -> None:
    ctx = BoundedConversationalPremiseContext(max_turns=4)
    p = premise(
        "mira::moved::book",
        subject="mira",
        relation="moved",
        object="book",
        turn=3,
    )
    ctx.admit_turn(turn=3, input_text="Mira moved the book.", premises=[p])

    eligible = ctx.eligible()
    assert len(eligible) == 1
    assert eligible[0].origin == "bounded-dialogue-turn"
    assert eligible[0].authority.cognitive_memory is False
    assert eligible[0].authority.semantic_truth is False
    assert ctx.authority_audit()["native_reasoning_required_for_answer_selection"] is True


def test_conflicting_property_values_remain_visible_without_forced_winner() -> None:
    ctx = BoundedConversationalPremiseContext()
    red = premise("box::is::red", subject="box", relation="is", object="red", turn=1)
    blue = premise("box::is::blue", subject="box", relation="is", object="blue", turn=1)

    ctx.admit_turn(
        turn=1,
        input_text="The box is red. The box is blue.",
        premises=[red, blue],
    )

    eligible = ctx.eligible()
    assert {p.status for p in eligible} == {"conflict"}
    assert {p.object for p in eligible} == {"red", "blue"}
    assert red.canonical in blue.conflict_with
    assert blue.canonical in red.conflict_with


def test_explicit_correction_supersedes_only_bounded_same_relation_premise_and_preserves_provenance() -> None:
    ctx = BoundedConversationalPremiseContext()
    old = premise("box::is::red", subject="box", relation="is", object="red", turn=1)
    ctx.admit_turn(turn=1, input_text="The box is red.", premises=[old])
    ctx.eligible()

    corrected = premise(
        "box::is::blue",
        subject="box",
        relation="is",
        object="blue",
        turn=2,
        correction=True,
    )
    ctx.admit_turn(
        turn=2,
        input_text="Correction: the box is blue.",
        premises=[corrected],
    )

    assert old.status == "superseded"
    assert corrected.status == "active"
    assert old.canonical in corrected.supersedes
    assert old in ctx.premises  # provenance/history is retained, not rewritten
    assert [p.object for p in ctx.eligible(include_conflicts=False)] == ["blue"]


def test_context_expiry_is_bounded_and_does_not_replay_old_turns() -> None:
    ctx = BoundedConversationalPremiseContext(max_turns=2)
    p1 = premise("a::is::one", subject="a", relation="is", object="one", turn=1)
    p2 = premise("b::is::two", subject="b", relation="is", object="two", turn=2)
    p3 = premise("c::is::three", subject="c", relation="is", object="three", turn=3)

    ctx.admit_turn(turn=1, input_text="A is one.", premises=[p1])
    ctx.admit_turn(turn=2, input_text="B is two.", premises=[p2])
    ctx.admit_turn(turn=3, input_text="C is three.", premises=[p3])

    assert p1.status == "expired"
    assert p2.status != "expired"
    assert p3.status != "expired"
    assert p1 not in ctx.eligible()


def test_stale_audit_is_rejected_and_native_trace_is_observational_evidence_only() -> None:
    ctx = BoundedConversationalPremiseContext()
    p = premise("mira::opened::door", subject="mira", relation="opened", object="door", turn=9)
    p.native_trace = NativeGeometryTrace(
        irg_event_ids=("irg:9",),
        dkt_activation_ids=("dkt:42",),
        egr_region_ids=("egr:r2",),
        rl_proof_ids=("rl:p7",),
        frenet_trace_ids=("fr:3",),
    )
    ctx.admit_turn(turn=9, input_text="Mira opened the door.", premises=[p])

    assert p.native_trace.has_native_trace is True
    assert p.authority.answer is False
    ctx.require_fresh_audit(turn=9, input_text="Mira opened the door.")
    with pytest.raises(RuntimeError, match="stale current-turn"):
        ctx.require_fresh_audit(turn=10, input_text="Why did Mira open the door?")
