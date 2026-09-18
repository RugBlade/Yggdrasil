import inspect

from noeron.cognition.models import SpeechActDevelopmentState
from noeron.orchestrator import Noeron


def test_fresh_m4c2_speech_act_state_still_has_zero_fabricated_observations():
    st=SpeechActDevelopmentState()
    assert st.action_pre_knots == {}
    assert st.action_post_knots == {}
    assert st.action_observations == {}
    assert st.transition_observations == 0
    assert st.pending_action == ""
    assert st.pending_pre_knot is None
    assert st.pending_pre_residual is None
    assert st.operator_calibration_observations == 0
    assert st.last_outcome_audit == {}


def test_runtime_resolution_outcome_uses_native_consistency_and_security_gates():
    src=inspect.getsource(Noeron._resolve_pending_speech_act_outcome)
    assert "_communication_consistency_residual" in src
    assert "result.state.dkt.security_admissible" in src
    assert "_nonworsening" in src
    assert "InitiativePolicy._mean" in src
    assert "observe_resolution_transition" in src
    assert "observed-environment-response" in src


def test_mark_pending_does_not_claim_choice_or_owner_preference():
    src=inspect.getsource(Noeron._mark_speech_act_pending)
    assert "native_choice_claim':False" in src
    assert "preference_label_authority':False" in src
    assert "relationship_authority':False" in src
    assert "invalid resolution speech act" in src


def test_observational_selector_does_not_secretly_mark_an_action_pending():
    src=inspect.getsource(Noeron._resolution_speech_act_selection)
    assert "_mark_speech_act_pending" not in src
    assert "changes_outward_transport':False" in src
    assert "changes_native_content':False" in src


def test_ingest_resolves_prior_pending_outcome_before_current_selection():
    src=inspect.getsource(Noeron.ingest)
    resolve=src.index("_resolve_pending_speech_act_outcome")
    thought=src.index("thought=self.cognition.response")
    select=src.index("_resolution_speech_act_selection")
    assert resolve < thought < select


def test_mark_pending_is_infrastructure_for_future_actual_execution_only():
    src=inspect.getsource(Noeron._mark_speech_act_pending)
    assert "only after a speech-act actuator has actually executed" in src
    assert "explicit authenticated calibration" in src
