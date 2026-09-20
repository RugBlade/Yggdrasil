"""Disposable integration contract; not a published HF2 runtime candidate.

Typed identity and route confidence are evidence. Neither chooses content or acts.
The existing audit policy is reused with injective structural node encodings.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import json

from two_ledger_v2 import build_ledger, canonical, digest
from noeron.inference import proposition_key, _relation_matches, _spatial_relation
from noeron.math.models import LogicalProposition, InferenceStep
from noeron.conversation_proof import AmbiguityConstraint
from noeron.conversation_runtime_gate import gate_inference_candidates, RuntimeProofGateResult, _zero_authority


def typed_id(key):
    return json.dumps(['proof-node-v1', *key], ensure_ascii=False, separators=(',', ':'))


def admit(rows, mode):
    """Keep the established admission order separate from unordered proof closure.

    Reasoning historically keeps the last representative in the first insertion
    position. Use that representative for correction control only, retaining all
    admitted observations. Direct infer historically applies corrections in input
    order. No representative confidence is used for proof aggregation.
    """
    if mode not in ('direct', 'reasoning'):
        raise ValueError('unknown admission mode')
    grouped = {}
    for i, p in enumerate(rows):
        grouped.setdefault(proposition_key(p), []).append(i)
    groups = (list(grouped.values()) if mode == 'reasoning' else [[i] for i in range(len(rows))])
    active, audit = {}, []
    for indexes in groups:
        control = rows[indexes[-1]]
        key = proposition_key(control)
        if 'correction' in control.modifiers:
            removed = [k for k in active if k != key and (k[0], k[1], k[4], k[5]) == (key[0], key[1], key[4], key[5])]
            for old in removed:
                audit.append({'kind': 'bounded-correction-supersession', 'old_key': old,
                    'new_key': key, 'removed_input_indexes': active.pop(old),
                    'control_input_index': indexes[-1], 'role': 'admission-event-not-formal-proof',
                    'semantic_truth_authority': False, 'answer_authority': False})
        active.setdefault(key, []).extend(indexes)
    admitted_indexes = sorted({i for indexes in active.values() for i in indexes})
    return admitted_indexes, audit


@dataclass
class InferenceResult:
    derived: list
    steps: list
    candidates: list
    status: str
    ledger: object
    propositions: list
    admitted_indexes: list
    admission_audit: list

    def __iter__(self):
        return iter((self.derived, self.steps, self.candidates, self.status))

    def __len__(self):
        return 4

    def __getitem__(self, index):
        return tuple(self)[index]


def infer_compatible(rows, query, *, max_steps=128, max_proof_records=1024, admission_mode='direct'):
    rows = list(rows)
    indexes, admission_audit = admit(rows, admission_mode)
    ledger = build_ledger([rows[i] for i in indexes], max_conclusion_steps=max_steps,
                          max_proof_records=max_proof_records, admission_complete=True)
    producers = {k: [r for r in ledger.records if tuple(r['conclusion_key']) == k] for k in ledger.keys}
    observations = {k: [s for s in ledger.sources.values() if tuple(s['key']) == k] for k in ledger.keys}
    # There is deliberately no recursively selected producer. A scalar is exposed
    # only for a single direct observation or one already-numeric direct route.
    # Nested/cyclic/multiple support remains a finite symbolic reference graph.
    known = {}
    for key in ledger.keys:
        ss, rr = observations[key], producers[key]
        readings = [v for s in ss for v in s['confidence_readings']]
        if len(ss) == 1 and len(readings) == 1 and not rr:
            value, status = readings[0], 'single-observed-source'
        elif not ss and len(rr) == 1 and rr[0]['confidence']['value'] is not None:
            value, status = rr[0]['confidence']['value'], 'single-direct-route-existing-conjunction'
        else:
            value, status = None, 'unaggregated-support'
        if not ledger.proof_ledger_complete:
            value, status = None, 'incomplete-proof-ledger'
        confidence = {'value': value, 'status': status,
            'source_ids': sorted(s['source_id'] for s in ss),
            'producer_record_ids': sorted(r['record_id'] for r in rr), 'cross_route_reducer': None}
        # Source/memory fields are set only where unique, never picked by ordering.
        source_fields = {}
        for name in ('source', 'source_record_id', 'source_memory_id'):
            values = {s[name] for s in ss if s.get(name)}
            source_fields[name] = next(iter(values)) if len(values) == 1 else ''
        source_fields['source_memory_ids'] = sorted({x for s in ss for x in s['source_memory_ids']})
        known[key] = LogicalProposition(subject=key[0], relation=key[1], object=key[2],
            polarity=key[3], universal=key[4], modality=key[5], confidence=value,
            derived=key not in ledger.premise_keys, proof_node_key=list(key),
            proof_confidence=confidence, **source_fields)
    steps = [InferenceStep(rule=r['rule'],
        premises=[canonical(k) for k in r['premise_keys'] + r['rule_evidence_keys']],
        conclusion=canonical(r['conclusion_key']), confidence=r['confidence']['value'], proof_record=r)
        for r in ledger.records]
    derived = [p for k, p in known.items() if k not in ledger.premise_keys]
    candidates = select_query(known, ledger, query)
    if not ledger.proof_ledger_complete:
        candidates, status = [], 'proof-gated-incomplete-ledger'
    elif len(candidates) == 1:
        status = ('unique-proof-supported-negative-answer' if query.kind == 'exact-proposition' and not candidates[0].polarity
                  else 'unique-proof-supported-answer')
    elif candidates:
        status = 'multiple-proof-supported-answers-no-forced-choice'
    else:
        status = ('no-logical-selection-requested' if query.kind in {'none','unresolved-surface-question','unresolved-reference'}
                  else 'no-proof-supported-answer')
    return InferenceResult(derived, steps, candidates, status, ledger, list(known.values()), indexes, admission_audit)


def select_query(known, ledger, query):
    rows = list(known.values())
    kind = query.kind
    match = lambda p: _relation_matches(p.relation, query.relation)
    if kind == 'derive-all':
        return [p for p in rows if p.derived]
    if kind == 'relation-between':
        return [p for p in rows if p.subject == query.subject and p.object == query.object]
    if kind == 'relation-from-subject':
        return [p for p in rows if p.subject == query.subject and match(p)]
    if kind == 'relation-to-object':
        return [p for p in rows if p.object == query.object and match(p)]
    if kind == 'exact-proposition':
        return [p for p in rows if p.subject == query.subject and p.object == query.object and match(p)]
    if kind == 'why-proposition':
        targets = {k for k,p in known.items() if p.subject == query.subject and p.object == query.object and match(p)}
        support = {tuple(k) for r in ledger.records if tuple(r['conclusion_key']) in targets
                   for k in r['premise_keys'] + r['rule_evidence_keys']}
        target_text = {canonical(k) for k in targets}
        support.update(k for k,p in known.items() if p.polarity and p.relation in {'causes','explains'} and p.object in target_text)
        return [p for k,p in known.items() if k in support and k not in targets]
    if kind == 'copular-value-from-subject':
        return [p for p in rows if p.polarity and p.subject == query.subject and p.relation == 'is']
    if kind == 'relation-subjects':
        return [p for p in rows if p.polarity and match(p)]
    if kind == 'where-from-subject':
        return [p for p in rows if p.subject == query.subject and _spatial_relation(p.relation) and match(p)]
    if kind in {'when-from-subject','how-from-subject'}:
        prefix = 'time-' if kind.startswith('when-') else 'manner-'
        return [p for p in rows if p.subject == query.subject and p.relation.startswith(prefix) and match(p)]
    return []


@dataclass(frozen=True)
class AuditNode:
    proposition: object
    def canonical(self):
        return typed_id(proposition_key(self.proposition))


def gate_compatible(result, query, bindings, ambiguities=(), *, candidates=None):
    candidates = list(result.candidates if candidates is None else candidates)
    if not result.ledger.proof_ledger_complete:
        return RuntimeProofGateResult((), 'proof-gated-incomplete-ledger',
            ({'proof_ledger_complete': False, 'support_gate_passed': False,
              'semantic_truth_authority': False, 'answer_authority': False},), len(candidates), _zero_authority())
    # Bind each envelope to its actual typed input, before any canonical collapse.
    premises = [replace(envelope, canonical=typed_id(proposition_key(p))) for p,envelope in bindings]
    projected = [dict(rule=r['rule'], conclusion=typed_id(r['conclusion_key']),
        premises=[typed_id(k) for k in r['premise_keys'] + r['rule_evidence_keys']],
        confidence=r['confidence']['value']) for r in result.ledger.records]
    # Legacy ambiguity scope is broad: expand to EVERY typed node with that text.
    # Do not select a typed interpretation of an underspecified legacy scope.
    aliases = {}
    for k in result.ledger.keys:
        aliases.setdefault(canonical(k), []).append(typed_id(k))
    scoped = [replace(a, affected_canonicals=tuple(v for c in a.affected_canonicals
              for v in aliases.get(c, [c]))) for a in ambiguities]
    targets = [p for p in result.propositions if p.subject == query.subject and p.object == query.object
               and _relation_matches(p.relation, query.relation)]
    audit = gate_inference_candidates(query_kind=query.kind, candidates=[AuditNode(p) for p in candidates],
        provenance_premises=premises, inference_steps=projected, ambiguities=scoped,
        why_targets=[AuditNode(p) for p in targets] if query.kind == 'why-proposition' else (),
        block_unscoped_ambiguity=True)
    return replace(audit, eligible_candidates=tuple(p.proposition for p in audit.eligible_candidates),
        audits=tuple({**a, 'proof_ledger_complete': True, 'identity_encoding': 'proof-node-v1',
            'canonical_aliases': aliases} for a in audit.audits))


def workspace_confidence(result, answers, query, geometric_value, has_memory):
    import math
    context = ([p for p in result.propositions if p.subject == query.subject and p.object == query.object
                and _relation_matches(p.relation, query.relation)] if query.kind == 'why-proposition' else answers)
    if not result.ledger.proof_ledger_complete or any(p.confidence is None for p in context):
        return None, {'status': 'incomplete-or-unaggregated-proof-support', 'cross_route_reducer': None,
                      'geometric_support': geometric_value}
    if not answers:
        return geometric_value, {'status': 'existing-geometry-only', 'cross_route_reducer': None}
    if any(p.confidence is None for p in answers):
        return None, {'status': 'unaggregated-proof-support', 'cross_route_reducer': None}
    # Existing workspace conjunction of answer premises, only when all operands
    # are defined. It is never a reducer of parallel routes to one proposition.
    proof = min(p.confidence for p in answers)
    value = math.sqrt(max(0.0,min(1.0,proof*geometric_value))) if has_memory else proof
    return value, {'status': 'existing-defined-workspace-conjunction', 'cross_route_reducer': None}
