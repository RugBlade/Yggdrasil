from pathlib import Path


PATCH = Path("patches/hf2/0004-hf2-proof-provenance-ambiguity-runtime-gate.patch")


def text():
    return PATCH.read_text(encoding="utf-8")


def test_patch_targets_expected_runtime_layers():
    p = text()
    for path in (
        "src/noeron/inference.py",
        "src/noeron/math/models.py",
        "src/noeron/reasoning.py",
        "src/noeron/math/kernel.py",
        "src/noeron/orchestrator.py",
    ):
        assert path in p


def test_patch_exposes_transparent_why_target_helper_not_second_surface_parser():
    p = text()
    assert "def query_target_propositions" in p
    assert "_relation_matches(p.relation, query.relation)" in p
    assert "query_target_propositions(premises+derived,query)" in p


def test_patch_preserves_three_provenance_classes():
    p = text()
    assert "origin='current-turn'" in p
    assert "origin='dkt-retrieved-persistent'" in p
    assert "tuple(bounded_selected)+tuple(persistent_provenance)+tuple(current_provenance)" in p


def test_patch_uses_post_closure_native_geometry_before_proof_gate():
    p = text()
    assert "post_closure_knot=post_closure_knot" in p
    assert "active_region_ids=active_region_ids" in p
    assert "dkt_support_knot=(post_closure_knot.model_dump" in p
    assert "select_bounded_premises_by_native_geometry" in p


def test_patch_gates_current_ambiguity_conservatively():
    p = text()
    assert "ambiguity_constraints_from_structure" in p
    assert "current_language_parse_audit=irg_state.language_parse_audit" in p
    assert "block_unscoped_ambiguity=True" in p
    assert "irg-unresolved-reference" in p


def test_patch_requires_actual_explanation_for_why():
    p = text()
    assert "why_targets=query_target_propositions" in p
    assert "query_kind=query.kind" in p
    assert "why_targets=why_targets" in p
    assert "gate_inference_candidates" in p


def test_patch_filters_support_without_candidate_ranking_authority():
    p = text()
    assert "proof_gate_authority" in p
    assert "'answer': False" in p
    assert "'speech_act': False" in p
    assert "'candidate_ranking': False" in p
    assert "answers=list(proof_gate.eligible_candidates)" in p


def test_read_only_structure_observation_precedes_math_update():
    p = text()
    pre = p.index("current_structure={}")
    observe = p.index("current_structure=self.language.dialogue_structure")
    update = p.index("result=self.math.update")
    assert pre < observe < update


def test_current_turn_admission_still_occurs_after_math_update():
    p = text()
    update = p.index("result=self.math.update")
    admit = p.index("current_bridge=admit_live_current_turn")
    assert update < admit
    assert "current_turn_index=next_conversational_turn" in p
    assert "turn=int(self.state.conversational_turn)" in p


def test_patch_reuses_same_current_structure_for_math_and_reply_local_audit():
    p = text()
    assert "current_language_structure=current_structure" in p
    assert "structure=current_structure" in p


def test_patch_records_proof_audit_in_reasoning_state():
    p = text()
    for field in (
        "proof_support_audits",
        "proof_gate_status",
        "proof_gate_blocked_candidate_count",
        "proof_gate_unscoped_ambiguity_count",
        "proof_gate_authority",
    ):
        assert field in p


def test_patch_has_no_terra_or_canned_clarification_fallback():
    p = text().lower()
    assert "terra" not in p
    assert "i don't know" not in p
    assert "i do not know" not in p
    assert "please clarify" not in p


def test_patch_does_not_move_current_turn_into_bounded_history_before_update():
    p = text()
    before_update = p[: p.index("result=self.math.update")]
    assert "admit_live_current_turn(" not in before_update
    assert "_hf2_conversation_premises.admit_turn" not in before_update
