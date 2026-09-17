from dataclasses import dataclass

from noeron.conversation_premises import ConversationalPremiseEnvelope
from noeron.conversation_proof import AmbiguityConstraint
from noeron.conversation_runtime_gate import gate_inference_candidates


@dataclass
class P:
    value: str

    def canonical(self) -> str:
        return self.value


def env(canonical, *, turn=1, status="active", conflict_with=()):
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
    )


def step(rule, premises, conclusion):
    return {"rule": rule, "premises": list(premises), "conclusion": conclusion, "confidence": 1.0}


def test_ordinary_supported_candidate_survives_without_ranking_authority():
    target = P("lamp::is::on")
    result = gate_inference_candidates(
        query_kind="exact-proposition",
        candidates=[target],
        provenance_premises=[env(target.canonical())],
        inference_steps=[],
    )
    assert result.eligible_candidates == (target,)
    assert result.status == "proof-gate-all-candidates-auditable"
    assert result.authority["answer"] is False
    assert result.authority["candidate_ranking"] is False


def test_multiple_supported_candidates_are_preserved_jointly():
    a = P("box::is::red")
    b = P("box::is::blue")
    result = gate_inference_candidates(
        query_kind="copular-value-from-subject",
        candidates=[a, b],
        provenance_premises=[env(a.canonical()), env(b.canonical())],
        inference_steps=[],
        block_unscoped_ambiguity=False,
    )
    assert result.eligible_candidates == (a, b)
    assert result.blocked_candidate_count == 0


def test_unscoped_live_ambiguity_conservatively_blocks_answer_candidate():
    candidate = P("sara::won::race")
    ambiguity = AmbiguityConstraint(
        ambiguity_id="pronoun-she",
        kind="reference",
        alternatives=("mira", "sara"),
    )
    result = gate_inference_candidates(
        query_kind="relation-from-subject",
        candidates=[candidate],
        provenance_premises=[env(candidate.canonical())],
        inference_steps=[],
        ambiguities=[ambiguity],
        block_unscoped_ambiguity=True,
    )
    assert result.eligible_candidates == ()
    assert result.status == "proof-gated-unresolved-ambiguity"


def test_conflicted_support_is_filtered_not_arbitrarily_ranked():
    candidate = P("box::is::red")
    result = gate_inference_candidates(
        query_kind="exact-proposition",
        candidates=[candidate],
        provenance_premises=[env(candidate.canonical(), status="conflict", conflict_with=("box::is::blue",))],
        inference_steps=[],
    )
    assert result.eligible_candidates == ()
    assert result.status == "proof-gated-unresolved-conflict"


def test_why_event_truth_cannot_be_its_own_explanation():
    event = P("mira::opened::door")
    # Deliberately mimic the old defect by offering the event itself as the answer.
    result = gate_inference_candidates(
        query_kind="why-proposition",
        candidates=[event],
        why_targets=[event],
        provenance_premises=[env(event.canonical())],
        inference_steps=[],
    )
    assert result.eligible_candidates == ()
    assert result.status in {"proof-gated-incomplete-provenance", "proof-gated-missing-causal-support"}


def test_why_actual_derivation_keeps_explanatory_premises_jointly_available():
    antecedent = P("lamp::is::on")
    implication = P("lamp-rule::implies::room-bright")
    event = P("room::is::bright")
    result = gate_inference_candidates(
        query_kind="why-proposition",
        candidates=[antecedent, implication],
        why_targets=[event],
        provenance_premises=[env(antecedent.canonical()), env(implication.canonical())],
        inference_steps=[step("structured-modus-ponens", [antecedent.canonical(), implication.canonical()], event.canonical())],
    )
    assert result.eligible_candidates == (antecedent, implication)
    assert result.status == "proof-gate-why-support-auditable"
    assert result.authority["answer"] is False


def test_why_missing_target_is_no_answer_not_fallback():
    explanation = P("mira::because::rain")
    result = gate_inference_candidates(
        query_kind="why-proposition",
        candidates=[explanation],
        why_targets=[],
        provenance_premises=[env(explanation.canonical())],
        inference_steps=[],
    )
    assert result.eligible_candidates == ()
    assert result.status == "proof-gated-missing-why-target"


def test_derived_ordinary_candidate_requires_all_leaf_provenance():
    antecedent = "lamp::is::on"
    missing_rule = "lamp-rule::implies::room-bright"
    target = P("room::is::bright")
    result = gate_inference_candidates(
        query_kind="exact-proposition",
        candidates=[target],
        provenance_premises=[env(antecedent)],
        inference_steps=[step("structured-modus-ponens", [antecedent, missing_rule], target.canonical())],
    )
    assert result.eligible_candidates == ()
    assert result.status == "proof-gated-incomplete-provenance"
