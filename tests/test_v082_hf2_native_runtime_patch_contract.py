from pathlib import Path


PATCH = Path("patches/hf2/0003-hf2-native-bounded-dialogue-reasoning.patch")


def text() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_patch_targets_only_expected_runtime_reasoning_surfaces():
    s = text()
    for path in (
        "src/noeron/math/models.py",
        "src/noeron/reasoning.py",
        "src/noeron/math/kernel.py",
        "src/noeron/orchestrator.py",
    ):
        assert f"--- a/{path}" in s
    assert "src/noeron/llm.py" not in s
    assert "terra" not in s.lower()


def test_bounded_dialogue_enters_only_post_closure_reasoning_not_pre_egr_support():
    s = text()
    # The new argument is passed into the step-7 reasoning call.
    assert "post_closure_knot=core2" in s
    assert "bounded_dialogue_premises=bounded_dialogue_premises or []" in s
    # Pre-EGR support call remains the original geometry-only call in the patch;
    # there must be no authored replacement that injects dialogue there.
    assert "support=build_multi_memory_reasoning(experience,retrieved,bounded_dialogue" not in s


def test_runtime_uses_real_dkt_sobolev_distance_and_numerical_tie_policy():
    s = text()
    assert "dkt.sobolev_distance(KnotState.model_validate(a),KnotState.model_validate(b))" in s
    assert "tied_fn=numerically_tied" in s
    assert "limit=6" in s


def test_correction_control_does_not_escape_bounded_layer():
    s = text()
    assert "Do not pass the generic 'correction' control modifier" in s
    assert "bounded-correction" not in s  # no hidden global rewrite rule
    assert "modifiers=['bounded-dialogue-provenance',f'bounded-status:{row.status}']" in s


def test_current_turn_ir_g_and_persistent_dkt_premises_remain_present():
    s = text()
    assert "current_premises = [p.model_copy(deep=True)" in s
    assert "learned_premises = _learned_premises_for_retrieved" in s
    assert "bounded_premises + learned_premises + current_premises" in s


def test_orchestrator_passes_only_prior_eligible_dialogue_for_conversational_events():
    s = text()
    assert "bounded_dialogue_for_reasoning=()" in s
    assert "not event.metadata.get('endogenous')" in s
    assert "not event.metadata.get('nonconversational_observation')" in s
    assert "self._hf2_conversation_premises.eligible(include_conflicts=True)" in s


def test_math_state_carries_explicit_bounded_dialogue_audit_not_authority():
    s = text()
    for field in (
        "bounded_dialogue_premise_count",
        "bounded_dialogue_source_turns",
        "bounded_dialogue_distances",
        "bounded_dialogue_selection_status",
        "bounded_dialogue_missing_geometry_source_turns",
        "bounded_dialogue_invalid_distance_source_turns",
        "bounded_dialogue_conflict_count",
    ):
        assert field in s
    assert "bounded_dialogue_truth" not in s
    assert "bounded_dialogue_answer" not in s


def test_runtime_trace_states_full_native_order_before_bounded_proof_closure():
    s = text()
    assert "only after the regional EGR ->" in s
    assert "RL/Frenet -> DKT closure" in s
    assert "post-closure DKT-selected bounded dialogue working premises" in s
