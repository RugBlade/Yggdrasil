import inspect

from fastapi.testclient import TestClient

from noeron.api import app
from noeron.orchestrator import Noeron


def test_runtime_calibration_requires_authenticated_owner_at_api_boundary():
    routes={getattr(r,"path",""):r for r in app.routes}
    assert "/owner/resolution/calibrate" in routes
    src=inspect.getsource(routes["/owner/resolution/calibrate"].endpoint)
    assert "_require_owner" in src
    assert "owner_authenticated=True" in src


def test_runtime_calibration_is_explicitly_not_native_choice_or_relationship():
    src=inspect.getsource(Noeron.operator_resolution_calibration)
    assert "operator-directed-calibration-not-native-choice" in src
    assert "'native_choice_claim':False" in src
    assert "'relationship_authority':False" in src
    assert "'preference_label_authority':False" in src
    assert "'content_authority':False" in src
    assert "'transport_authority':False" in src


def test_runtime_uses_only_current_structured_and_native_question_content():
    src=inspect.getsource(Noeron.operator_resolution_calibration)
    assert "lang.dialogue,'last_structure'" in src
    assert "last_thought" in src
    assert "question_candidates" in src
    assert "build_operator_resolution_calibration" in src


def test_runtime_marks_pending_only_after_exposure_executed():
    src=inspect.getsource(Noeron.operator_resolution_calibration)
    executable=src.index("if not exposure.executable")
    mark=src.index("_mark_speech_act_pending")
    assert executable < mark
    assert "actually produced its grounded/nonsemantic result" in src


def test_runtime_refuses_to_overwrite_an_unresolved_pending_outcome():
    src=inspect.getsource(Noeron.operator_resolution_calibration)
    assert "if st.pending_action" in src
    assert "pending-outcome-already-exists" in src


def test_calibration_counter_is_audit_only_and_selector_remains_unchanged():
    calibration=inspect.getsource(Noeron.operator_resolution_calibration)
    selector=inspect.getsource(Noeron._resolution_speech_act_selection)
    assert "operator_calibration_observations" in calibration
    assert "operator_calibration_observations" not in selector
    assert "_mark_speech_act_pending" not in selector


def test_route_rejects_unauthenticated_request():
    client=TestClient(app)
    response=client.post("/owner/resolution/calibrate",json={"action":"defer"})
    assert response.status_code in {401,503}
