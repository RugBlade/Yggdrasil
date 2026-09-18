"""M4C3A behavioral gate. Synthetic fixtures are test-only, never observations.

No external service or canonical database is opened. Unit harnesses execute the
actual Noeron methods with real native models; integration tests use isolated
temporary SQLite and the real mathematical/cognition/language path.
"""
import hashlib
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from noeron.cognition.models import (
    MathematicalProvenance, NativeThought, NativeThoughtKind,
)
from noeron.development import NativeLanguageFaculty
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind, NoeronState
from noeron.orchestrator import Noeron

ACTS=("clarify","ask","defer","remain-silent")


@pytest.fixture
def runtime():
    n=Noeron.__new__(Noeron)
    n.state=NoeronState()
    n.state.math_kernel.dkt.core_knot=dkt.reference_knot()
    n._lock=RLock()
    n.language=NativeLanguageFaculty()
    n.store=SimpleNamespace(append_state=Mock())
    n.security=SimpleNamespace(checkpoint=Mock())
    return n


def native_turn(n, *, questions=("Where is the lamp?",), text="she moved it"):
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source="isolated-test",content=text)
    n.state.last_event_id=event.id
    n.state.conversational_turn+=1
    thought=NativeThought(
        kind=NativeThoughtKind.RESPONSE,statement="",
        question_candidates=list(questions),
        mathematical_provenance=MathematicalProvenance(source_event_id=event.id),
    )
    structure={
        "text_sha256":hashlib.sha256(text.encode()).hexdigest(),
        "ambiguities":[
            {"kind":"reference","surface":"she","candidates":["Mira","Sara"]},
            {"kind":"reference","surface":"it","candidates":["book","box"]},
        ],
    }
    n._cache_resolution_turn(event,thought,structure)
    return event,thought,structure


def assert_preview(n, action):
    before=n.state.model_dump()
    out=n.operator_resolution_calibration(action,owner_authenticated=True)
    assert out["executed"] is False
    assert out["native_choice_claim"] is False
    for key in ("relationship_authority","preference_label_authority",
                "content_authority","transport_authority","execution_authority"):
        assert out[key] is False
    assert n.state.model_dump()==before
    n.store.append_state.assert_not_called()
    n.security.checkpoint.assert_not_called()
    return out


def test_regression_stale_last_thought_is_not_current_content(runtime):
    # A spy isolates the legacy calibration call from its independent missing-
    # import failure, exposing whether stale content is actually returned.
    stale=NativeThought(
        kind=NativeThoughtKind.RESPONSE,statement="old",
        question_candidates=["Which old item?"],
        mathematical_provenance=MathematicalProvenance(source_event_id=uuid4()),
    )
    runtime.state.cognition.last_thought=stale
    runtime.state.last_event_id=uuid4()
    runtime._mark_speech_act_pending=Mock(return_value={"pending":False})
    before=runtime.state.model_dump()
    out=runtime.operator_resolution_calibration("ask",owner_authenticated=True)
    assert out["candidates"]==[]
    assert out["executed"] is False
    assert runtime.state.model_dump()==before
    runtime._mark_speech_act_pending.assert_not_called()


def test_regression_nonsemantic_preview_is_not_execution(runtime):
    before=runtime.state.model_dump()
    out=runtime.operator_resolution_calibration("defer",owner_authenticated=True)
    assert out["executed"] is False
    assert runtime.state.model_dump()==before


def test_regression_pending_marker_requires_event_identity(runtime):
    before=runtime.state.model_dump()
    out=runtime._mark_speech_act_pending("defer")
    assert out["pending"] is False
    assert out["status"]=="current-execution-event-required"
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize("action", ACTS)
def test_all_grounded_calibrations_remain_preview_only(runtime,action):
    event,_,_=native_turn(runtime)
    runtime._mark_speech_act_pending=Mock(side_effect=AssertionError("no execution occurred"))
    out=assert_preview(runtime,action)
    assert out["source_event_id"]==str(event.id)
    assert out["eligible"] is True
    assert out["status"]=="calibration-preview-only-actuator-not-connected"
    runtime._mark_speech_act_pending.assert_not_called()
    st=runtime.state.cognition.speech_act_development
    assert st.operator_calibration_observations==st.transition_observations==0
    assert st.pending_action==""
    assert st.action_observations=={}
    if action in {"defer","remain-silent"}:
        assert out["candidates"]==[]


def test_preview_preserves_all_unresolved_alternatives_without_selecting(runtime):
    native_turn(runtime)
    out=assert_preview(runtime,"clarify")
    assert [c["alternatives"] for c in out["candidates"]]==[["Mira","Sara"],["book","box"]]
    assert [c["focus_surface"] for c in out["candidates"]]==["she","it"]
    assert all(c["existing_question"]=="" for c in out["candidates"])


def test_preview_copies_current_native_questions_but_never_previous_thought(runtime):
    native_turn(runtime,questions=("What changed?",))
    runtime.state.cognition.last_thought=NativeThought(
        kind=NativeThoughtKind.OPEN_QUESTION,statement="previous",
        question_candidates=["Old question?"],
    )
    out=assert_preview(runtime,"ask")
    assert [c["existing_question"] for c in out["candidates"]]==["What changed?"]


def test_cache_is_a_snapshot_not_an_alias_of_mutable_dialogue_state(runtime):
    _,thought,structure=native_turn(runtime)
    thought.question_candidates.append("Later invention?")
    structure["ambiguities"][0]["candidates"].append("Later alternative")
    runtime.state.cognition.language.dialogue.last_structure=structure
    assert [c["existing_question"] for c in assert_preview(runtime,"ask")["candidates"]]==["Where is the lamp?"]
    assert assert_preview(runtime,"clarify")["candidates"][0]["alternatives"]==["Mira","Sara"]


@pytest.mark.parametrize("change", ["event","turn"])
def test_any_newer_native_turn_invalidates_old_preview(runtime,change):
    native_turn(runtime)
    if change=="event":
        runtime.state.last_event_id=uuid4()
    else:
        runtime.state.conversational_turn+=1
    out=assert_preview(runtime,"ask")
    assert out["candidates"]==[]
    assert out["status"]=="calibration-not-executed-no-current-turn-context"


@pytest.mark.parametrize("case", ["endogenous","nonconversational","empty","wrong-proof-event",
                                 "wrong-state-event","wrong-digest","autonomous-thought"])
def test_cache_fails_closed_and_clears_prior_turn(runtime,case):
    event,thought,structure=native_turn(runtime)
    if case=="endogenous": event.metadata["endogenous"]=True
    elif case=="nonconversational": event.metadata["nonconversational_observation"]=True
    elif case=="empty": event.content=""
    elif case=="wrong-proof-event": thought.mathematical_provenance.source_event_id=uuid4()
    elif case=="wrong-state-event": runtime.state.last_event_id=uuid4()
    elif case=="wrong-digest": structure["text_sha256"]="not-this-event"
    elif case=="autonomous-thought": thought.kind=NativeThoughtKind.OPEN_QUESTION
    runtime._cache_resolution_turn(event,thought,structure)
    assert runtime._hf2_resolution_turn is None
    assert assert_preview(runtime,"clarify")["candidates"]==[]


def test_empty_current_questions_do_not_resurrect_persistent_last_thought(runtime):
    native_turn(runtime,questions=())
    runtime.state.cognition.last_thought=NativeThought(
        kind=NativeThoughtKind.RESPONSE,statement="old",question_candidates=["Old?"],
    )
    out=assert_preview(runtime,"ask")
    assert out["eligible"] is False
    assert out["candidates"]==[]
    assert "no-existing-native-question-content" in out["content_status"]


def test_preview_cache_does_not_survive_state_serialization(runtime):
    native_turn(runtime)
    saved=runtime.state.model_dump_json()
    restored=Noeron.__new__(Noeron)
    restored.state=NoeronState.model_validate_json(saved)
    restored._lock=RLock()
    restored.store=SimpleNamespace(append_state=Mock())
    restored.security=SimpleNamespace(checkpoint=Mock())
    assert assert_preview(restored,"ask")["candidates"]==[]
    assert "Which old item?" not in saved
    assert "_hf2_resolution_turn" not in saved


@pytest.mark.parametrize("action", ["unknown","answer"])
def test_pending_marker_rejects_unknown_act_with_value_error(runtime,action):
    before=runtime.state.model_dump()
    with pytest.raises(ValueError,match="invalid resolution speech act"):
        runtime._mark_speech_act_pending(action)
    assert runtime.state.model_dump()==before


def test_pending_marker_cannot_overwrite_existing_outcome(runtime):
    event,_,_=native_turn(runtime)
    st=runtime.state.cognition.speech_act_development
    st.pending_action="ask"
    st.pending_event_id=uuid4()
    before=runtime.state.model_dump()
    out=runtime._mark_speech_act_pending("defer",event.id)
    assert out=={"pending":False,"status":"pending-outcome-already-exists"}
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize("event_kind", ["missing","stale"])
def test_pending_marker_rejects_unbound_or_old_execution_event(runtime,event_kind):
    native_turn(runtime)
    before=runtime.state.model_dump()
    out=runtime._mark_speech_act_pending("ask",None if event_kind=="missing" else uuid4())
    assert out["pending"] is False
    assert runtime.state.model_dump()==before


def test_legacy_calibration_origin_cannot_mark_pending_even_with_current_event(runtime):
    event,_,_=native_turn(runtime)
    before=runtime.state.model_dump()
    out=runtime._mark_speech_act_pending(
        "ask",event.id,origin="authenticated-owner-resolution-calibration",
    )
    assert out["pending"] is False
    assert out["status"]=="calibration-preview-is-not-execution"
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize("case", ["no-event","legacy-origin","same-event"])
def test_uncorroborated_legacy_or_same_event_outcome_cannot_train(runtime,case):
    event,_,_=native_turn(runtime)
    st=runtime.state.cognition.speech_act_development
    st.pending_action="defer"
    st.pending_pre_knot=runtime.state.math_kernel.dkt.core_knot.model_copy(deep=True)
    st.pending_pre_residual=0.0
    st.pending_event_id=None if case=="no-event" else (event.id if case=="same-event" else uuid4())
    st.pending_origin="authenticated-owner-resolution-calibration" if case=="legacy-origin" else "test-only"
    before=runtime.state.model_dump()
    out=runtime._resolve_pending_speech_act_outcome(SimpleNamespace(state=runtime.state.math_kernel),event)
    assert out["learned"] is False
    assert out["status"]=="unverified-or-nonlater-speech-act-outcome-not-learned"
    assert runtime.state.model_dump()==before  # preserve, do not erase legacy audit


@pytest.fixture
def isolated_runtime(tmp_path):
    # Full in-process instance on a new test-only database; no deployment access.
    return Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/"isolated.sqlite3"),terra_enabled=False)


def test_real_ingest_binds_even_an_empty_current_native_response(isolated_runtime):
    n=isolated_runtime
    n.state.cognition.last_thought=NativeThought(
        kind=NativeThoughtKind.RESPONSE,statement="old",question_candidates=["Stale?"],
    )
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source="isolated-test",content="What is a flarble?")
    reply=n.ingest(event)
    assert n._hf2_resolution_turn["event_id"]==event.id
    assert n._hf2_resolution_turn["questions"]==()
    before=n.state.model_dump()
    out=n.operator_resolution_calibration("ask",owner_authenticated=True)
    assert out["executed"] is False and out["candidates"]==[]
    assert n.state.model_dump()==before
    assert reply.speech_act_audit["native_choice_claim"] is False
    assert n.state.cognition.speech_act_development.action_observations=={}


@pytest.mark.parametrize("nonconversational", [True,False])
def test_real_ingest_invalidates_preview_for_nonconversation_or_rejection(isolated_runtime,nonconversational):
    n=isolated_runtime
    first=CognitiveEvent(kind=EventKind.USER_MESSAGE,source="isolated-test",content="What is a flarble?")
    n.ingest(first)
    assert n._hf2_resolution_turn is not None
    event=CognitiveEvent(
        kind=EventKind.OBSERVATION if nonconversational else EventKind.USER_MESSAGE,
        source="isolated-test",content="Next observation",
        metadata={"nonconversational_observation":nonconversational},
    )
    changes=None if nonconversational else {"identity":"unexpected-overwrite"}
    reply=n.ingest(event,proposed_invariant_changes=changes)
    if not nonconversational: assert reply.security.allowed is False
    assert n._hf2_resolution_turn is None
    assert n.operator_resolution_calibration("ask",owner_authenticated=True)["candidates"]==[]


def test_real_proof_supported_answer_is_not_reclassified_by_preview(isolated_runtime):
    n=isolated_runtime
    event=CognitiveEvent(
        kind=EventKind.USER_MESSAGE,source="isolated-test",
        content="The lamp is on. Is the lamp on?",
    )
    reply=n.ingest(event)
    assert n.state.math_kernel.reasoning.answer_candidates
    assert reply.speech_act_audit["requires_resolution"] is False
    assert reply.speech_act_audit["native_choice_claim"] is False
    before=n.state.model_dump()
    out=n.operator_resolution_calibration("defer",owner_authenticated=True)
    assert out["executed"] is False and out["candidates"]==[]
    assert n.state.model_dump()==before


@pytest.mark.parametrize("action", ACTS)
def test_authenticated_http_route_returns_preview_not_execution(runtime,monkeypatch,action):
    import noeron.api as api
    from fastapi.testclient import TestClient
    from noeron.auth import OwnerAuthenticator

    native_turn(runtime)
    token="isolated-m4c3a-test-owner-token-not-a-deployment-secret"
    monkeypatch.setattr(api,"owner_auth",OwnerAuthenticator(token))
    monkeypatch.setattr(api,"noeron",runtime)
    before=runtime.state.model_dump()
    response=TestClient(api.app).post(
        "/owner/resolution/calibrate",json={"action":action},
        headers={"X-Noeron-Owner-Token":token},
    )
    assert response.status_code==200
    out=response.json()
    assert out["authenticated_owner"] is True
    assert out["executed"] is False and out["native_choice_claim"] is False
    assert out["execution_authority"] is False
    assert runtime.state.model_dump()==before
    runtime.store.append_state.assert_not_called()
    runtime.security.checkpoint.assert_not_called()
