from noeron.conversation_premises import ConversationalPremiseEnvelope, NativeGeometryTrace
from noeron.conversation_proof import (
    AmbiguityConstraint,
    audit_proof_support,
    ambiguity_constraints_from_structure,
    proof_audit_summary,
)


def row(canonical, *, turn=1, status="active", conflict_with=(), trace=None):
    negative = canonical.startswith("not ")
    core = canonical[4:] if negative else canonical
    subject, relation, obj = core.split("::", 2)
    return ConversationalPremiseEnvelope(
        canonical=canonical,
        subject=subject,
        relation=relation,
        object=obj,
        polarity=not negative,
        source_turn=turn,
        origin="bounded-dialogue-turn",
        status=status,
        conflict_with=tuple(conflict_with),
        native_trace=trace or NativeGeometryTrace(),
    )


def step(rule, premises, conclusion, confidence=1.0):
    return {
        "rule": rule,
        "premises": list(premises),
        "conclusion": conclusion,
        "confidence": confidence,
    }


def test_direct_event_truth_is_valid_support_but_not_a_why_explanation():
    target = "mira::opened::door"
    ordinary = audit_proof_support(target, premises=[row(target)])
    assert ordinary.status == "proof-support-auditable"
    assert ordinary.support_gate_passed is True

    why = audit_proof_support(target, premises=[row(target)], require_explanation=True)
    assert why.status == "explanation-missing-causal-support"
    assert why.explanation_support is False
    assert why.support_gate_passed is False


def test_actual_derivation_supplies_explanatory_support_without_answer_authority():
    antecedent = "lamp::is::on"
    implication = "lamp::is::on::implies-proposition::room::is::bright"
    target = "room::is::bright"
    audit = audit_proof_support(
        target,
        premises=[row(antecedent), row(implication)],
        inference_steps=[step("structured-modus-ponens", [antecedent, implication], target)],
        require_explanation=True,
    )
    assert audit.status == "proof-support-auditable"
    assert audit.explanation_support is True
    assert set(audit.leaf_premises) == {antecedent, implication}
    assert audit.step_rules == ("structured-modus-ponens",)
    assert audit.authority["answer"] is False


def test_unresolved_ambiguity_blocks_only_when_proof_depends_on_affected_canonical():
    support = "mira::told::sara"
    target = "sara::won::race"
    constraint = AmbiguityConstraint(
        ambiguity_id="pronoun-she-1",
        kind="reference",
        affected_canonicals=(support,),
        alternatives=("mira", "sara"),
    )
    audit = audit_proof_support(
        target,
        premises=[row(support)],
        inference_steps=[step("reference-dependent-rule", [support], target)],
        ambiguities=[constraint],
    )
    assert audit.status == "proof-unresolved-ambiguity"
    assert audit.unresolved_ambiguity_ids == ("pronoun-she-1",)
    assert audit.support_gate_passed is False


def test_unrelated_or_unscoped_ambiguity_is_audited_without_fake_dependency():
    target = "lamp::is::on"
    structure = {
        "ambiguities": [
            {"id": "a-unscoped", "kind": "event-role", "alternatives": ["x", "y"]},
            {"id": "a-other", "kind": "reference", "affected_canonicals": ["book::is::blue"]},
        ]
    }
    constraints = ambiguity_constraints_from_structure(structure)
    audit = audit_proof_support(target, premises=[row(target)], ambiguities=constraints)
    assert audit.status == "proof-support-auditable"
    assert audit.unscoped_ambiguity_ids == ("a-unscoped",)
    assert audit.unresolved_ambiguity_ids == ()


def test_resolved_ambiguity_does_not_block_support():
    target = "sara::won::race"
    constraint = AmbiguityConstraint(
        ambiguity_id="resolved-ref",
        kind="reference",
        affected_canonicals=(target,),
        alternatives=("mira", "sara"),
        resolved=True,
    )
    audit = audit_proof_support(target, premises=[row(target)], ambiguities=[constraint])
    assert audit.status == "proof-support-auditable"


def test_conflicting_bounded_premise_cannot_silently_become_proof_support():
    target = "box::is::red"
    audit = audit_proof_support(
        target,
        premises=[row(target, status="conflict", conflict_with=("box::is::blue",))],
    )
    assert audit.status == "proof-unresolved-conflict"
    assert audit.conflicting_support == (target,)
    assert audit.support_gate_passed is False


def test_independent_uncontested_duplicate_support_is_not_poisoned_by_bounded_conflict():
    target = "box::is::red"
    conflicted = row(target, turn=2, status="conflict", conflict_with=("box::is::blue",))
    uncontested = row(target, turn=3, status="active")
    audit = audit_proof_support(target, premises=[conflicted, uncontested])
    assert audit.status == "proof-support-auditable"
    assert audit.conflicting_support == ()
    assert len(audit.provenance) == 2


def test_derived_proof_with_missing_leaf_provenance_is_rejected():
    target = "room::is::bright"
    audit = audit_proof_support(
        target,
        premises=[row("lamp::is::on")],
        inference_steps=[
            step(
                "structured-modus-ponens",
                ["lamp::is::on", "lamp-rule::implies::room-bright"],
                target,
            )
        ],
    )
    assert audit.status == "proof-incomplete-provenance"
    assert audit.missing_provenance == ("lamp-rule::implies::room-bright",)


def test_native_irg_dkt_egr_rl_frenet_evidence_is_aggregated_not_promoted_to_truth():
    target = "room::is::bright"
    trace = NativeGeometryTrace(
        irg_event_ids=("irg-1",),
        dkt_activation_ids=("dkt-1",),
        egr_region_ids=("egr-1",),
        rl_proof_ids=("rl-1",),
        frenet_trace_ids=("fr-1",),
        dkt_support_knot={"sobolev_order": 2},
    )
    audit = audit_proof_support(target, premises=[row(target, trace=trace)])
    assert audit.native_evidence == {
        "irg_event_ids": ("irg-1",),
        "dkt_activation_ids": ("dkt-1",),
        "egr_region_ids": ("egr-1",),
        "rl_proof_ids": ("rl-1",),
        "frenet_trace_ids": ("fr-1",),
    }
    assert audit.status == "proof-support-auditable"
    assert audit.authority["semantic_truth"] is False
    assert audit.authority["answer"] is False
    assert audit.authority["speech_act"] is False


def test_explicit_explanation_support_is_distinct_from_target_event_truth():
    target = "mira::opened::door"
    explanation = "mira::reason-for-opening::fresh-air"
    audit = audit_proof_support(
        target,
        premises=[row(target), row(explanation)],
        require_explanation=True,
        explanatory_support_canonicals=[explanation],
    )
    assert audit.explanation_support is True
    assert audit.status == "proof-support-auditable"


def test_explicit_explanation_name_without_provenance_is_rejected():
    target = "mira::opened::door"
    explanation = "mira::reason-for-opening::fresh-air"
    audit = audit_proof_support(
        target,
        premises=[row(target)],
        require_explanation=True,
        explanatory_support_canonicals=[explanation],
    )
    assert audit.explanation_support is True
    assert audit.status == "proof-incomplete-provenance"
    assert audit.missing_provenance == (explanation,)
    assert audit.support_gate_passed is False


def test_summary_preserves_native_path_and_zero_authority():
    target = "lamp::is::on"
    summary = proof_audit_summary(audit_proof_support(target, premises=[row(target)]))
    assert summary["native_reasoning_path"] == "IRG->DKT->regional-EGR->RL/Frenet->DKT->native-cognition/action"
    assert summary["authority"]["answer"] is False
    assert summary["authority"]["cognitive_memory"] is False
