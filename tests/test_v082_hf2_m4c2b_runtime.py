"""Behavioral contracts that remain valid across 0007 and its corrective successor."""
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from noeron.api import app
from noeron.models import NoeronState
from noeron.orchestrator import Noeron


def shell():
    runtime=Noeron.__new__(Noeron)
    runtime.state=NoeronState()
    runtime._lock=RLock()
    runtime.store=SimpleNamespace(append_state=Mock())
    runtime.security=SimpleNamespace(checkpoint=Mock())
    return runtime


@pytest.mark.parametrize("action", ["clarify", "ask", "defer", "remain-silent"])
def test_direct_calibration_requires_authenticated_owner_without_mutation(action):
    runtime=shell()
    before=runtime.state.model_dump()
    with pytest.raises(ValueError, match="authenticated owner"):
        runtime.operator_resolution_calibration(action)
    assert runtime.state.model_dump()==before
    runtime.store.append_state.assert_not_called()
    runtime.security.checkpoint.assert_not_called()


@pytest.mark.parametrize("action", ["answer", "express", ""])
def test_unknown_calibration_act_is_rejected_without_mutation(action):
    runtime=shell()
    before=runtime.state.model_dump()
    with pytest.raises(ValueError, match="unsupported resolution calibration action"):
        runtime.operator_resolution_calibration(action, owner_authenticated=True)
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize("action", ["clarify", "ask", "defer", "remain-silent"])
def test_pending_calibration_is_not_overwritten(action):
    runtime=shell()
    runtime.state.cognition.speech_act_development.pending_action="ask"
    before=runtime.state.model_dump()
    out=runtime.operator_resolution_calibration(action, owner_authenticated=True)
    assert out["executed"] is False
    assert "pending-outcome-already-exists" in out["status"]
    assert out["native_choice_claim"] is False
    assert runtime.state.model_dump()==before


def test_absent_native_question_never_authors_calibration_fallback():
    runtime=shell()
    before=runtime.state.model_dump()
    out=runtime.operator_resolution_calibration("ask", owner_authenticated=True)
    assert out["executed"] is False
    assert out["candidates"]==[]
    assert runtime.state.model_dump()==before


def test_real_route_rejects_unauthenticated_request():
    response=TestClient(app).post("/owner/resolution/calibrate", json={"action":"defer"})
    assert response.status_code in {401,503}
