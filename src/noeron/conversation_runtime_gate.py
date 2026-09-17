"""HF2 runtime adapter between transparent inference and proof-provenance audit.

This module filters *support-ineligible* inference candidates. It never ranks the
remaining candidates and never chooses a final answer or speech act. All candidates
that survive proof/provenance/ambiguity checks remain jointly available to the
native consequence machinery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from noeron.conversation_premises import ConversationalPremiseEnvelope
from noeron.conversation_proof import (
    AmbiguityConstraint,
    ProofSupportAudit,
    audit_proof_support,
    proof_audit_summary,
)


def _canonical(row: object) -> str:
    fn = getattr(row, "canonical", None)
    if callable(fn):
        return str(fn() or "").strip()
    return str(getattr(row, "canonical", "") or "").strip()


@dataclass(frozen=True)
class RuntimeProofGateResult:
    eligible_candidates: tuple[object, ...]
    status: str
    audits: tuple[dict[str, object], ...]
    blocked_candidate_count: int
    authority: dict[str, bool]


def gate_inference_candidates(
    *,
    query_kind: str,
    candidates: Sequence[object],
    provenance_premises: Iterable[ConversationalPremiseEnvelope],
    inference_steps: Iterable[object],
    ambiguities: Iterable[AmbiguityConstraint] = (),
    why_targets: Sequence[object] = (),
    block_unscoped_ambiguity: bool = True,
) -> RuntimeProofGateResult:
    """Retain only proof-support-eligible candidates without ranking them.

    For ordinary queries each candidate's proposition is audited as the proof target.
    For ``why-proposition`` the candidate list represents explanatory support while
    ``why_targets`` contains the event/property proposition(s) being explained. The
    event itself is explicitly removed from its own explanatory-support set, so event
    truth can never pass as a reason merely by being true.
    """
    premises = tuple(provenance_premises)
    steps = tuple(inference_steps)
    ambiguity_rows = tuple(ambiguities)
    answer_rows = tuple(candidates)
    audits: list[ProofSupportAudit] = []

    if not answer_rows:
        return RuntimeProofGateResult(
            eligible_candidates=(),
            status="proof-gate-no-inference-candidates",
            audits=(),
            blocked_candidate_count=0,
            authority=_zero_authority(),
        )

    if str(query_kind) == "why-proposition":
        targets = tuple(why_targets)
        if not targets:
            return RuntimeProofGateResult(
                eligible_candidates=(),
                status="proof-gated-missing-why-target",
                audits=(),
                blocked_candidate_count=len(answer_rows),
                authority=_zero_authority(),
            )
        raw_explanations = tuple(c for c in (_canonical(row) for row in answer_rows) if c)
        for target in targets:
            target_canonical = _canonical(target)
            if not target_canonical:
                continue
            # Critical H9 invariant: P cannot explain why P merely because P is a
            # supported event. Other explicit explanatory candidates and genuine
            # inference ancestry remain available without ranking.
            explanation_canonicals = tuple(c for c in raw_explanations if c != target_canonical)
            audits.append(
                audit_proof_support(
                    target_canonical,
                    premises=premises,
                    inference_steps=steps,
                    ambiguities=ambiguity_rows,
                    require_explanation=True,
                    explanatory_support_canonicals=explanation_canonicals,
                    block_unscoped_ambiguity=block_unscoped_ambiguity,
                )
            )
        passed = [audit for audit in audits if audit.support_gate_passed]
        eligible = answer_rows if passed else ()
        status = "proof-gate-why-support-auditable" if passed else _blocked_status(audits)
        return RuntimeProofGateResult(
            eligible_candidates=tuple(eligible),
            status=status,
            audits=tuple(proof_audit_summary(audit) for audit in audits),
            blocked_candidate_count=(0 if passed else len(answer_rows)),
            authority=_zero_authority(),
        )

    eligible: list[object] = []
    for candidate in answer_rows:
        canonical = _canonical(candidate)
        if not canonical:
            continue
        audit = audit_proof_support(
            canonical,
            premises=premises,
            inference_steps=steps,
            ambiguities=ambiguity_rows,
            block_unscoped_ambiguity=block_unscoped_ambiguity,
        )
        audits.append(audit)
        if audit.support_gate_passed:
            eligible.append(candidate)

    if len(eligible) == len(answer_rows):
        status = "proof-gate-all-candidates-auditable"
    elif eligible:
        status = "proof-gate-partial-candidates-auditable"
    else:
        status = _blocked_status(audits)
    return RuntimeProofGateResult(
        eligible_candidates=tuple(eligible),
        status=status,
        audits=tuple(proof_audit_summary(audit) for audit in audits),
        blocked_candidate_count=max(0, len(answer_rows) - len(eligible)),
        authority=_zero_authority(),
    )


def _blocked_status(audits: Sequence[ProofSupportAudit]) -> str:
    statuses = {audit.status for audit in audits}
    if "proof-unresolved-ambiguity" in statuses:
        return "proof-gated-unresolved-ambiguity"
    if "proof-unresolved-conflict" in statuses:
        return "proof-gated-unresolved-conflict"
    if "proof-incomplete-provenance" in statuses:
        return "proof-gated-incomplete-provenance"
    if "explanation-missing-causal-support" in statuses:
        return "proof-gated-missing-causal-support"
    if "proof-missing-support" in statuses:
        return "proof-gated-missing-support"
    return "proof-gated-no-auditable-support"


def _zero_authority() -> dict[str, bool]:
    return {
        "semantic_truth": False,
        "answer": False,
        "speech_act": False,
        "candidate_ranking": False,
        "cognitive_memory": False,
        "relationship": False,
        "source_write": False,
        "deployment": False,
    }
