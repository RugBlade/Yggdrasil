from types import SimpleNamespace

import pytest

from noeron.conversation_actions import (
    RESOLUTION_AFFORDANCES,
    observe_resolution_transition,
)


def state():
    return SimpleNamespace(
        action_pre_knots={},
        action_post_knots={},
        action_observations={},
        transition_observations=0,
    )


def mean(old, new, n):
    if old is None or n <= 0:
        return float(new)
    return (float(old) * n + float(new)) / float(n + 1)


def test_observed_admitted_transition_updates_only_empirical_geometry():
    st=state()
    out=observe_resolution_transition(
        st,"clarify",1.0,3.0,admissible=True,mean_fn=mean,
        source="observed-environment-response:test",
    )
    assert out["learned"] is True
    assert st.action_pre_knots["clarify"] == 1.0
    assert st.action_post_knots["clarify"] == 3.0
    assert st.action_observations["clarify"] == 1
    assert st.transition_observations == 1
    assert out["preference_label_authority"] is False
    assert out["semantic_truth_authority"] is False
    assert out["relationship_authority"] is False


def test_repeated_observations_use_injected_mean_not_authored_reward():
    st=state()
    observe_resolution_transition(st,"ask",2.0,4.0,admissible=True,mean_fn=mean)
    observe_resolution_transition(st,"ask",4.0,8.0,admissible=True,mean_fn=mean)
    assert st.action_pre_knots["ask"] == 3.0
    assert st.action_post_knots["ask"] == 6.0
    assert st.action_observations["ask"] == 2
    assert st.transition_observations == 2


def test_rejected_post_state_does_not_train():
    st=state()
    out=observe_resolution_transition(
        st,"defer",1.0,9.0,admissible=False,mean_fn=mean,
    )
    assert out["learned"] is False
    assert st.action_pre_knots == {}
    assert st.action_post_knots == {}
    assert st.action_observations == {}
    assert st.transition_observations == 0


def test_unknown_affordance_is_rejected():
    with pytest.raises(ValueError):
        observe_resolution_transition(
            state(),"answer",0.0,1.0,admissible=True,mean_fn=mean,
        )


def test_every_resolution_affordance_can_be_observed_without_becoming_choice_label():
    for action in RESOLUTION_AFFORDANCES:
        st=state()
        out=observe_resolution_transition(
            st,action,0.0,1.0,admissible=True,mean_fn=mean,
        )
        assert out["learned"] is True
        assert out["speech_act_selection_authority"] is False
        assert out["owner_preference_authority"] is False
