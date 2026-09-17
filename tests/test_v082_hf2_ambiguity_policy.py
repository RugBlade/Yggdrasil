from noeron.conversation_premises import ConversationalPremiseEnvelope
from noeron.conversation_proof import AmbiguityConstraint, audit_proof_support


def row(canonical: str):
    subject, relation, obj = canonical.split("::", 2)
    return ConversationalPremiseEnvelope(
        canonical=canonical,
        subject=subject,
        relation=relation,
        object=obj,
        polarity=True,
        source_turn=1,
        origin="bounded-dialogue-turn",
    )


def test_unscoped_ambiguity_can_be_conservatively_gated_by_live_runtime():
    target = "sara::won::race"
    ambiguity = AmbiguityConstraint(
        ambiguity_id="embedded-pronoun",
        kind="reference",
        alternatives=("mira", "sara"),
    )
    audit = audit_proof_support(
        target,
        premises=[row(target)],
        ambiguities=[ambiguity],
        block_unscoped_ambiguity=True,
    )
    assert audit.status == "proof-unresolved-ambiguity"
    assert audit.unscoped_ambiguity_ids == ("embedded-pronoun",)
    assert audit.support_gate_passed is False


def test_unscoped_ambiguity_remains_audit_only_when_caller_can_tolerate_it():
    target = "lamp::is::on"
    ambiguity = AmbiguityConstraint(
        ambiguity_id="unrelated-unscoped",
        kind="event-role",
        alternatives=("candidate-a", "candidate-b"),
    )
    audit = audit_proof_support(target, premises=[row(target)], ambiguities=[ambiguity])
    assert audit.status == "proof-support-auditable"
    assert audit.unscoped_ambiguity_ids == ("unrelated-unscoped",)


def test_scoped_ambiguity_blocks_regardless_of_unscoped_policy_flag():
    target = "sara::won::race"
    ambiguity = AmbiguityConstraint(
        ambiguity_id="scoped-ref",
        kind="reference",
        affected_canonicals=(target,),
        alternatives=("mira", "sara"),
    )
    audit = audit_proof_support(target, premises=[row(target)], ambiguities=[ambiguity])
    assert audit.status == "proof-unresolved-ambiguity"
    assert audit.unresolved_ambiguity_ids == ("scoped-ref",)
