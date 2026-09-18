"""M4C3F: local non-content execution receipts for native defer/remain-silent.

Synthetic consequence geometry below is test-only. Speech-act selection itself still
uses the real DKT consequence selector; the new receipt has no choice authority.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from noeron.cognition import models as cm
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind, NoeronState
from noeron.orchestrator import Noeron


@pytest.fixture
def runtime(tmp_path):
    return Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "isolated.sqlite3"), terra_enabled=False)


def seed_resolution_geometry(n, target):
    context = n.state.math_kernel.dkt.core_knot
    st = n.state.cognition.speech_act_development
    for i, action in enumerate(("clarify", "ask", "defer", "remain-silent"), 1):
        pre = context.model_copy(deep=True)
        if action != target:
            pre.c0[0] += i * 0.2
        pre.invariant_signature = dkt.invariant_signature(pre)
        st.action_pre_knots[action] = pre
        st.action_post_knots[action] = context.model_copy(deep=True)
        st.action_observations[action] = 1
    st.transition_observations = 4


def select_noncontent(n, action):
    event = CognitiveEvent(kind=EventKind.USER_MESSAGE, source="m4c3f-test", content="What is a flarble?")
    n.state.last_event_id = event.id
    n.state.conversational_turn = max(1, int(n.state.conversational_turn))
    reasoning = n.state.math_kernel.reasoning
    reasoning.logical_query.kind = "property-of"
    reasoning.logical_query.raw = event.content
    reasoning.answer_candidates = []
    reasoning.answer_selection_status = "no-proof-supported-answer"
    reasoning.proof_gate_status = "proof-gated-no-answer"
    reasoning.proof_gate_unscoped_ambiguity_count = 0
    thought = cm.NativeThought(
        kind=cm.NativeThoughtKind.RESPONSE,
        statement="",
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id),
    )
    seed_resolution_geometry(n, action)
    audit = n._resolution_speech_act_selection(
        thought,
        SimpleNamespace(state=n.state.math_kernel),
        event=event,
        current_structure=analyze_dialogue_structure(event.content),
    )
    assert audit["action"] == action
    assert audit["native_choice_claim"] is True
    assert audit["decision_layer"] == "learned-deliberative"
    assert audit["content_formation"]["status"] == "selected-nonsemantic-act-no-content-or-execution"
    assert n._hf2_resolution_observation is None
    return event, audit


def later_result(n):
    state = n.state.math_kernel.model_copy(deep=True)
    state.dkt.security_admissible = True
    state.egr.bridge_residual = 0.0
    state.egr.balance_residual = 0.0
    state.rl.geodesic_acceleration_norm = 0.0
    return SimpleNamespace(state=state)


@pytest.mark.parametrize(
    "action,effect",
    [
        ("defer", "defer-current-turn-resolution"),
        ("remain-silent", "close-current-turn-without-outward-realization"),
    ],
)
def test_native_noncontent_choice_commits_only_local_no_message_receipt(runtime, action, effect):
    event, _ = select_noncontent(runtime, action)
    before_observations = dict(runtime.state.cognition.speech_act_development.action_observations)
    out = runtime._commit_noncontent_resolution_execution(event)
    assert out["receipt_recorded"] is out["executed"] is True
    assert out["status"] == "local-noncontent-action-committed"
    assert out["effect"] == effect
    assert out["content_emitted"] is out["outward_transport_performed"] is False
    assert out["peer_delivery_confirmed"] is False
    assert out["peer_read_confirmed"] is False
    assert out["peer_understanding_confirmed"] is False
    assert out["peer_reply_causation_confirmed"] is False

    st = runtime.state.cognition.speech_act_development
    receipt = st.pending_execution_receipt
    assert isinstance(receipt, cm.NonContentResolutionExecutionReceipt)
    assert receipt.action == st.pending_action == action
    assert receipt.effect == effect
    assert receipt.channel == "local-runtime-noncontent"
    assert receipt.content_emitted is receipt.outward_transport_performed is False
    assert receipt.peer_delivery_confirmed is False
    assert receipt.peer_read_confirmed is False
    assert receipt.peer_understanding_confirmed is False
    assert receipt.peer_reply_causation_confirmed is False
    assert st.pending_origin == "native-resolution-local-noncontent-completed"
    assert st.action_observations == before_observations
    assert runtime.state.cognition.initiative_development.pending_expression_pre_knot is None
    assert runtime.state.cognition.initiative_development.pending_expression_receipt_id is None
    assert runtime._hf2_resolution_dispatch is None
    assert runtime.store.latest_state().cognition.speech_act_development.pending_execution_receipt == receipt
    assert runtime.security.restore().cognition.speech_act_development.pending_execution_receipt == receipt


@pytest.mark.parametrize("action", ["defer", "remain-silent"])
def test_noncontent_receipt_roundtrips_without_becoming_transport_or_expression(runtime, action):
    event, _ = select_noncontent(runtime, action)
    runtime._commit_noncontent_resolution_execution(event)
    saved = NoeronState.model_validate_json(runtime.state.model_dump_json())
    receipt = saved.cognition.speech_act_development.pending_execution_receipt
    assert isinstance(receipt, cm.NonContentResolutionExecutionReceipt)
    assert receipt.action == action
    assert receipt.outward_transport_performed is False
    assert saved.cognition.initiative_development.pending_expression_pre_knot is None
    assert saved.cognition.initiative_development.pending_expression_receipt_id is None


@pytest.mark.parametrize("action", ["defer", "remain-silent"])
def test_only_later_admitted_conversation_can_learn_from_local_noncontent_execution(runtime, action):
    original, _ = select_noncontent(runtime, action)
    runtime._commit_noncontent_resolution_execution(original)
    st = runtime.state.cognition.speech_act_development
    receipt = st.pending_execution_receipt
    before = st.action_observations[action]
    later = CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="later-test",
        content="New information.",
        created_at=receipt.completed_at + timedelta(seconds=1),
    )
    out = runtime._resolve_pending_speech_act_outcome(later_result(runtime), later)
    assert out["learned"] is True
    assert out["action"] == action
    assert out["execution_receipt"]["status"] == "local-noncontent-action-committed"
    assert out["execution_receipt"]["peer_delivery_confirmed"] is False
    assert st.action_observations[action] == before + 1
    assert st.pending_action == "" and st.pending_execution_receipt is None
    assert runtime._resolve_pending_speech_act_outcome(later_result(runtime), later) is None


@pytest.mark.parametrize("case", ["same-event", "tampered-effect", "endogenous", "nonconversational"])
def test_noncontent_receipt_never_manufactures_later_outcome(runtime, case):
    original, _ = select_noncontent(runtime, "defer")
    runtime._commit_noncontent_resolution_execution(original)
    st = runtime.state.cognition.speech_act_development
    receipt = st.pending_execution_receipt
    event = CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="later-test",
        content="Later.",
        created_at=receipt.completed_at + timedelta(seconds=1),
    )
    if case == "same-event":
        event.id = original.id
    elif case == "tampered-effect":
        st.pending_execution_receipt = receipt.model_copy(
            update={"effect": "close-current-turn-without-outward-realization"}
        )
    elif case == "endogenous":
        event.metadata["endogenous"] = True
    elif case == "nonconversational":
        event.metadata["nonconversational_observation"] = True
    before = runtime.state.model_dump()
    out = runtime._resolve_pending_speech_act_outcome(later_result(runtime), event)
    assert out["learned"] is False
    assert runtime.state.model_dump() == before


def test_serialized_or_client_like_noncontent_receipt_cannot_mark_execution(runtime):
    event, _ = select_noncontent(runtime, "defer")
    st = runtime.state.cognition.speech_act_development
    receipt = cm.NonContentResolutionExecutionReceipt(
        event_id=event.id,
        turn=runtime.state.conversational_turn,
        action="defer",
        effect="defer-current-turn-resolution",
        pre_knot_sha256=runtime._resolution_knot_digest(runtime.state.math_kernel.dkt.core_knot),
        pre_residual=runtime._communication_consistency_residual(runtime.state.math_kernel),
    )
    before = runtime.state.model_dump()
    out = runtime._mark_speech_act_pending(
        "defer",
        event.id,
        "learned-deliberative",
        "native-resolution-local-noncontent-completed",
        execution_receipt=receipt,
    )
    assert out["pending"] is False and "receipt-required" in out["status"]
    assert runtime.state.model_dump() == before
    assert st.pending_action == ""


@pytest.mark.parametrize(
    "flag",
    ["owner_command", "operator_realization_override", "nonconversational_observation"],
)
def test_privileged_or_nonconversational_metadata_cannot_turn_selection_into_local_execution(runtime, flag):
    event, _ = select_noncontent(runtime, "defer")
    event.metadata[flag] = True
    before = runtime.state.model_dump()
    out = runtime._commit_noncontent_resolution_execution(event)
    assert out["executed"] is False
    assert out["status"] == "current-ordinary-conversational-event-required"
    assert runtime.state.model_dump() == before


def test_noncontent_persistence_failure_restores_state_and_security(runtime, monkeypatch):
    event, _ = select_noncontent(runtime, "remain-silent")
    before = runtime.state.model_dump()
    checkpoint = runtime.security.restore().model_dump()
    monkeypatch.setattr(
        runtime.store,
        "append_state",
        Mock(side_effect=OSError("isolated database failure")),
    )
    with pytest.raises(OSError, match="database failure"):
        runtime._commit_noncontent_resolution_execution(event)
    assert runtime.state.model_dump() == before
    assert runtime.security.restore().model_dump() == checkpoint
    assert runtime._hf2_receipt_to_mark is None
