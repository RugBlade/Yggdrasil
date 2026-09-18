from noeron.conversation_actions import (
    RESOLUTION_AFFORDANCES,
    choose_resolution_act,
    resolution_affordances,
)


def authority_false(row):
    assert row["semantic_truth"] is False
    assert row["answer"] is False
    assert row["candidate_ranking"] is False
    assert row["cognitive_memory"] is False
    assert row["relationship"] is False
    assert row["native_content_generation"] is False
    assert row["source_write"] is False
    assert row["deployment"] is False


def test_supported_answer_does_not_invoke_resolution_layer():
    e = resolution_affordances(
        query_kind="exact-proposition",
        proof_gate_status="unique-proof-supported-answer",
        ambiguity_count=0,
        native_question_count=0,
        answer_candidate_count=1,
    )
    assert e.requires_resolution is False
    assert e.eligible_actions == ()
    authority_false(e.authority)
    assert e.authority["speech_act_selection"] is False


def test_ambiguity_does_not_directly_choose_clarify():
    e = resolution_affordances(
        query_kind="relation-to-object",
        proof_gate_status="proof-gated-unscoped-ambiguity",
        ambiguity_count=2,
        native_question_count=1,
        answer_candidate_count=0,
    )
    assert e.requires_resolution is True
    assert set(e.eligible_actions) == {"clarify", "ask", "defer", "remain-silent"}
    authority_false(e.authority)
    assert e.authority["speech_act_selection"] is False


def test_clarify_not_eligible_without_native_question_content():
    e = resolution_affordances(
        query_kind="who-from-object",
        proof_gate_status="proof-gated-unscoped-ambiguity",
        ambiguity_count=1,
        native_question_count=0,
        answer_candidate_count=0,
    )
    assert "clarify" not in e.eligible_actions
    assert "ask" not in e.eligible_actions
    assert set(e.eligible_actions) == {"defer", "remain-silent"}
    assert "clarify-not-eligible-without-native-question-content" in e.reasons


def test_remain_silent_is_affordance_not_default_choice():
    e = resolution_affordances(
        query_kind="why-proposition",
        proof_gate_status="proof-gated-missing-why-target",
        ambiguity_count=0,
        native_question_count=0,
        answer_candidate_count=0,
    )
    assert "remain-silent" in e.eligible_actions
    out = choose_resolution_act(
        eligible_actions=["remain-silent"],
        context_geometry=0.0,
        action_pre_geometry={"remain-silent": 0.0},
        action_post_geometry={"remain-silent": 0.0},
        action_observations={"remain-silent": 10},
        transport_fn=lambda pre, post, current: current + (post-pre),
        reference_fn=lambda posts, obs, acts: (0.0, tuple(acts)),
        distance_fn=lambda a, b: abs(a-b),
        tied_fn=lambda a, b: a == b,
    )
    assert out["action"] is None
    assert out["native_choice_claim"] is False
    assert out["selection_status"] == "unresolved-insufficient-independent-affordances"


def test_missing_geometry_for_any_eligible_action_stays_unresolved():
    out = choose_resolution_act(
        eligible_actions=["defer", "remain-silent"],
        context_geometry=2.0,
        action_pre_geometry={"defer": 0.0, "remain-silent": None},
        action_post_geometry={"defer": 1.0, "remain-silent": None},
        action_observations={"defer": 3, "remain-silent": 0},
        transport_fn=lambda pre, post, current: current + (post-pre),
        reference_fn=lambda posts, obs, acts: (0.0, tuple(acts)),
        distance_fn=lambda a, b: abs(a-b),
        tied_fn=lambda a, b: a == b,
    )
    assert out["action"] is None
    assert out["native_choice_claim"] is False
    assert out["missing_consequence_actions"] == ["remain-silent"]


def test_exact_geometry_tie_stays_unresolved():
    out = choose_resolution_act(
        eligible_actions=["defer", "remain-silent"],
        context_geometry=0.0,
        action_pre_geometry={"defer": 0.0, "remain-silent": 0.0},
        action_post_geometry={"defer": -1.0, "remain-silent": 1.0},
        action_observations={"defer": 2, "remain-silent": 2},
        transport_fn=lambda pre, post, current: current + (post-pre),
        reference_fn=lambda posts, obs, acts: (0.0, tuple(acts)),
        distance_fn=lambda a, b: abs(a-b),
        tied_fn=lambda a, b: abs(a-b) <= 1e-12,
    )
    assert out["action"] is None
    assert out["native_choice_claim"] is False
    assert set(out["tied_actions"]) == {"defer", "remain-silent"}


def test_unique_minimum_can_be_claimed_native():
    out = choose_resolution_act(
        eligible_actions=["defer", "remain-silent"],
        context_geometry=2.0,
        action_pre_geometry={"defer": 1.0, "remain-silent": 1.0},
        action_post_geometry={"defer": 1.5, "remain-silent": 5.0},
        action_observations={"defer": 4, "remain-silent": 4},
        transport_fn=lambda pre, post, current: current + (post-pre),
        reference_fn=lambda posts, obs, acts: (2.5, tuple(acts)),
        distance_fn=lambda a, b: abs(a-b),
        tied_fn=lambda a, b: abs(a-b) <= 1e-12,
    )
    assert out["action"] == "defer"
    assert out["native_choice_claim"] is True
    assert out["decision_layer"] == "learned-deliberative"
    assert out["selection_status"] == "native-unique-speech-act-predicted-post-state-hs-minimum"


def test_selector_never_generates_utterance_content():
    out = choose_resolution_act(
        eligible_actions=["ask", "remain-silent"],
        context_geometry=0.0,
        action_pre_geometry={"ask": 0.0, "remain-silent": 0.0},
        action_post_geometry={"ask": 0.2, "remain-silent": 0.8},
        action_observations={"ask": 1, "remain-silent": 1},
        transport_fn=lambda pre, post, current: current + (post-pre),
        reference_fn=lambda posts, obs, acts: (0.2, tuple(acts)),
        distance_fn=lambda a, b: abs(a-b),
        tied_fn=lambda a, b: a == b,
    )
    assert out["action"] == "ask"
    assert "text" not in out
    assert "utterance" not in out
    authority_false(out["authority"])


def test_affordance_set_is_bounded_and_contains_no_answer_act():
    assert RESOLUTION_AFFORDANCES == (
        "clarify",
        "ask",
        "defer",
        "remain-silent",
    )
    assert "answer" not in RESOLUTION_AFFORDANCES
    assert "express" not in RESOLUTION_AFFORDANCES
