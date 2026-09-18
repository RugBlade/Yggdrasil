import inspect

from noeron.cognition.models import GeometricCognitionState, SpeechActDevelopmentState
from noeron.models import NoeronReply
from noeron.orchestrator import Noeron


def test_fresh_speech_act_state_has_no_fabricated_consequence_observations():
    st = SpeechActDevelopmentState()
    assert st.action_pre_knots == {}
    assert st.action_post_knots == {}
    assert st.action_observations == {}
    assert st.transition_observations == 0
    assert st.last_selected_action == ""
    assert st.last_native_choice_claim is False


def test_geometric_cognition_persists_separate_speech_act_state_by_default():
    c = GeometricCognitionState()
    assert isinstance(c.speech_act_development, SpeechActDevelopmentState)
    assert c.speech_act_development is not c.initiative_development
    assert "Separate unresolved-response" in c.speech_act_development.note


def test_reply_exposes_read_only_speech_act_audit_field():
    assert "speech_act_audit" in NoeronReply.model_fields


def test_runtime_selector_injects_actual_native_math_machinery_not_carrier_metric():
    src = inspect.getsource(Noeron._resolution_speech_act_selection)
    assert "result.state.dkt.core_knot" in src
    assert "InitiativePolicy._transport_transition" in src
    assert "equal_affordance_post_manifold" in src
    assert "dkt.sobolev_distance" in src
    assert "numerically_tied" in src
    assert "IRG-DKT-regional-EGR-RL-Frenet-DKT" in src


def test_programmed_eligibility_is_not_native_choice_authority():
    src = inspect.getsource(Noeron._resolution_speech_act_selection)
    assert "resolution_affordances" in src
    assert "choose_resolution_act" in src
    assert "native_choice_claim" in src
    assert "changes_outward_transport" in src
    assert "changes_native_content" in src


def test_m4b_is_observational_only_before_transport_coupling():
    src = inspect.getsource(Noeron.ingest)
    thought = src.index("thought=self.cognition.response")
    speech = src.index("_resolution_speech_act_selection")
    transport = src.index("_conversation_transport")
    assert thought < speech < transport
    assert "speech_act_audit=speech_act_audit" in src
