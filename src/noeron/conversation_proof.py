"""HF2 proof-provenance and ambiguity gate for conversational reasoning.

This carrier layer is deliberately non-authoritative. It audits whether a proposed
proof support has complete provenance, whether unresolved ambiguity or bounded
conflict contaminates that support, and whether a WHY target has explanatory
support distinct from the target event itself.

It does not choose truth, an answer, a speech act, memory, relationship meaning,
source writes, or deployment. It only prepares auditable support evidence for the
native downstream path:
IRG -> DKT -> regional EGR -> RL/Frenet -> DKT -> native cognition/action.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from noeron.conversation_premises import ConversationalPremiseEnvelope

NATIVE_REASONING_PATH = "IRG->DKT->regional-EGR->RL/Frenet->DKT->native-cognition/action"


def _field(row: object, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _seq(row: object, name: str) -> tuple[object, ...]:
    raw = _field(row, name, ()) or ()
    if isinstance(raw, (str, bytes)):
        return (raw,)
    try:
        return tuple(raw)
    except TypeError:
        return ()


@dataclass(frozen=True)
class ProofStepView:
    rule: str
    premises: tuple[str, ...]
    conclusion: str
    confidence: float = 1.0


@dataclass(frozen=True)
class AmbiguityConstraint:
    ambiguity_id: str
    kind: str
    affected_canonicals: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    resolved: bool = False


@dataclass(frozen=True)
class ProofSupportAudit:
    target: str
    support_nodes: tuple[str, ...]
    leaf_premises: tuple[str, ...]
    step_rules: tuple[str, ...]
    unresolved_ambiguity_ids: tuple[str, ...]
    unscoped_ambiguity_ids: tuple[str, ...]
    conflicting_support: tuple[str, ...]
    missing_provenance: tuple[str, ...]
    explanation_support: bool
    support_gate_passed: bool
    status: str
    native_evidence: dict[str, tuple[str, ...]]
    provenance: tuple[dict[str, object], ...]
    authority: dict[str, bool]


def normalize_inference_steps(steps: Iterable[object]) -> tuple[ProofStepView, ...]:
    out: list[ProofStepView] = []
    for raw in steps:
        rule = str(_field(raw, "rule", "") or "").strip()
        conclusion = str(_field(raw, "conclusion", "") or "").strip()
        premises = tuple(str(x).strip() for x in _seq(raw, "premises") if str(x).strip())
        if not rule or not conclusion:
            continue
        confidence = float(_field(raw, "confidence", 1.0) or 1.0)
        out.append(ProofStepView(rule=rule, premises=premises, conclusion=conclusion, confidence=confidence))
    return tuple(out)


def ambiguity_constraints_from_structure(structure: Mapping[str, object] | None) -> tuple[AmbiguityConstraint, ...]:
    """Extract only explicit ambiguity dependency metadata.

    The parser may preserve ambiguity without knowing which proof node it affects.
    Such rows remain *unscoped* and are audited but do not automatically poison an
    unrelated proof. A later parser/bridge can provide ``affected_canonicals`` or
    ``candidate_canonicals`` to make the dependency machine-checkable.
    """
    out: list[AmbiguityConstraint] = []
    for index, raw in enumerate(list((structure or {}).get("ambiguities") or [])):
        if not isinstance(raw, Mapping):
            continue
        affected_raw = raw.get("affected_canonicals") or raw.get("candidate_canonicals") or ()
        if isinstance(affected_raw, str):
            affected = (affected_raw,)
        else:
            affected = tuple(str(x) for x in affected_raw if str(x).strip())
        alternatives_raw = raw.get("alternatives") or raw.get("candidates") or ()
        if isinstance(alternatives_raw, str):
            alternatives = (alternatives_raw,)
        else:
            alternatives = tuple(str(x) for x in alternatives_raw if str(x).strip())
        ambiguity_id = str(raw.get("id") or f"ambiguity-{index}")
        out.append(
            AmbiguityConstraint(
                ambiguity_id=ambiguity_id,
                kind=str(raw.get("kind") or "unspecified"),
                affected_canonicals=affected,
                alternatives=alternatives,
                resolved=bool(raw.get("resolved", False)),
            )
        )
    return tuple(out)


def _proof_closure(target: str, steps: Sequence[ProofStepView]) -> tuple[set[str], list[ProofStepView]]:
    by_conclusion: dict[str, list[ProofStepView]] = {}
    for step in steps:
        by_conclusion.setdefault(step.conclusion, []).append(step)

    nodes: set[str] = set()
    used_steps: list[ProofStepView] = []
    stack = [target]
    expanded: set[str] = set()
    while stack:
        node = stack.pop()
        if node in expanded:
            continue
        expanded.add(node)
        nodes.add(node)
        producers = by_conclusion.get(node, ())
        for step in producers:
            used_steps.append(step)
            for premise in step.premises:
                if premise:
                    nodes.add(premise)
                    stack.append(premise)
    return nodes, used_steps


def audit_proof_support(
    target: str,
    *,
    premises: Iterable[ConversationalPremiseEnvelope],
    inference_steps: Iterable[object] = (),
    ambiguities: Iterable[AmbiguityConstraint] = (),
    require_explanation: bool = False,
    explanatory_support_canonicals: Iterable[str] = (),
) -> ProofSupportAudit:
    """Audit provenance and ambiguity for one candidate proof target.

    ``support_gate_passed`` means only that this support package is sufficiently
    auditable to continue into downstream native consequence reasoning. It is NOT an
    answer selection or a truth claim.
    """
    target = str(target or "").strip()
    if not target:
        raise ValueError("target canonical is required")

    premise_rows = tuple(premises)
    premise_by_canonical: dict[str, list[ConversationalPremiseEnvelope]] = {}
    for row in premise_rows:
        premise_by_canonical.setdefault(row.canonical, []).append(row)

    steps = normalize_inference_steps(inference_steps)
    support_nodes, used_steps = _proof_closure(target, steps)

    has_direct_target = target in premise_by_canonical
    has_derived_target = any(step.conclusion == target for step in steps)
    explicit_explanation = {str(x).strip() for x in explanatory_support_canonicals if str(x).strip()}
    explanation_support = bool(has_derived_target or explicit_explanation)

    # Explicit explanatory candidates are themselves support nodes. Their proof
    # ancestry and provenance must therefore be auditable too; merely naming a
    # canonical as an explanation never grants it support authority.
    for explanatory in sorted(explicit_explanation):
        extra_nodes, extra_steps = _proof_closure(explanatory, steps)
        support_nodes.update(extra_nodes)
        for step in extra_steps:
            if step not in used_steps:
                used_steps.append(step)

    leaves: set[str] = set()
    produced = {step.conclusion for step in used_steps}
    for node in support_nodes:
        if node not in produced or node in premise_by_canonical:
            leaves.add(node)
    if has_direct_target:
        leaves.add(target)

    missing_provenance = sorted(node for node in leaves if node not in premise_by_canonical)

    conflicting: set[str] = set()
    provenance_rows: list[dict[str, object]] = []
    irg: set[str] = set()
    dkt: set[str] = set()
    egr: set[str] = set()
    rl: set[str] = set()
    frenet: set[str] = set()
    for canonical in sorted(leaves):
        rows = list(premise_by_canonical.get(canonical, ()))
        # Parallel provenance may contain a bounded conflicting copy and an
        # independent uncontested current/persistent copy of the *same* canonical.
        # A conflict blocks this canonical only when every available provenance path
        # for it is conflicted. This prevents stale bounded conflict metadata from
        # poisoning an independently supported current-turn proposition.
        if rows and all(row.status == "conflict" or bool(row.conflict_with) for row in rows):
            conflicting.add(canonical)
        for row in rows:  # preserve parallel provenance in the audit
            row.authority.assert_bounded_safe()
            trace = row.native_trace
            irg.update(trace.irg_event_ids)
            dkt.update(trace.dkt_activation_ids)
            egr.update(trace.egr_region_ids)
            rl.update(trace.rl_proof_ids)
            frenet.update(trace.frenet_trace_ids)
            provenance_rows.append(
                {
                    "canonical": canonical,
                    "origin": row.origin,
                    "source_turn": int(row.source_turn),
                    "status": row.status,
                    "admitted": bool(row.admitted),
                    "semantic_truth_authority": False,
                    "answer_authority": False,
                    "cognitive_memory_authority": False,
                }
            )

    unresolved: set[str] = set()
    unscoped: set[str] = set()
    for ambiguity in ambiguities:
        if ambiguity.resolved:
            continue
        if not ambiguity.affected_canonicals:
            unscoped.add(ambiguity.ambiguity_id)
            continue
        if support_nodes.intersection(ambiguity.affected_canonicals):
            unresolved.add(ambiguity.ambiguity_id)

    if not has_direct_target and not has_derived_target:
        status = "proof-missing-support"
        passed = False
    elif missing_provenance:
        status = "proof-incomplete-provenance"
        passed = False
    elif unresolved:
        status = "proof-unresolved-ambiguity"
        passed = False
    elif conflicting:
        status = "proof-unresolved-conflict"
        passed = False
    elif require_explanation and not explanation_support:
        status = "explanation-missing-causal-support"
        passed = False
    else:
        status = "proof-support-auditable"
        passed = True

    return ProofSupportAudit(
        target=target,
        support_nodes=tuple(sorted(support_nodes)),
        leaf_premises=tuple(sorted(leaves)),
        step_rules=tuple(step.rule for step in used_steps),
        unresolved_ambiguity_ids=tuple(sorted(unresolved)),
        unscoped_ambiguity_ids=tuple(sorted(unscoped)),
        conflicting_support=tuple(sorted(conflicting)),
        missing_provenance=tuple(missing_provenance),
        explanation_support=explanation_support,
        support_gate_passed=passed,
        status=status,
        native_evidence={
            "irg_event_ids": tuple(sorted(irg)),
            "dkt_activation_ids": tuple(sorted(dkt)),
            "egr_region_ids": tuple(sorted(egr)),
            "rl_proof_ids": tuple(sorted(rl)),
            "frenet_trace_ids": tuple(sorted(frenet)),
        },
        provenance=tuple(provenance_rows),
        authority={
            "semantic_truth": False,
            "answer": False,
            "speech_act": False,
            "cognitive_memory": False,
            "relationship": False,
            "source_write": False,
            "deployment": False,
        },
    )


def proof_audit_summary(audit: ProofSupportAudit) -> dict[str, object]:
    return {
        "target": audit.target,
        "status": audit.status,
        "support_gate_passed": audit.support_gate_passed,
        "support_nodes": list(audit.support_nodes),
        "leaf_premises": list(audit.leaf_premises),
        "step_rules": list(audit.step_rules),
        "unresolved_ambiguity_ids": list(audit.unresolved_ambiguity_ids),
        "unscoped_ambiguity_ids": list(audit.unscoped_ambiguity_ids),
        "conflicting_support": list(audit.conflicting_support),
        "missing_provenance": list(audit.missing_provenance),
        "explanation_support": audit.explanation_support,
        "native_evidence": {k: list(v) for k, v in audit.native_evidence.items()},
        "provenance": list(audit.provenance),
        "native_reasoning_path": NATIVE_REASONING_PATH,
        "authority": dict(audit.authority),
    }
