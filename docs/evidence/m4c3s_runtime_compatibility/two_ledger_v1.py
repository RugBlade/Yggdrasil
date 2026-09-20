"""Disposable M4C3S design model. Not an installed Noeron inference replacement.

Imports only identity/query helpers from the hash-verified post0022 source.
Proposition identity has no scalar confidence. Direct records retain finite
support references and the existing within-route minimum, never a route reducer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Iterator

from noeron.inference import _from_canonical, _relation_matches, proposition_key
from noeron.math.models import InferenceStep
from noeron.conversation_runtime_gate import gate_inference_candidates

Key = tuple[str, str, str, bool, bool, str]
AUTHORITY = {name: False for name in (
    'semantic_truth', 'answer', 'speech_act', 'preference', 'relationship',
    'cognitive_memory', 'source_write', 'deployment', 'candidate_ranking')}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def canonical(key: Key) -> str:
    s, r, o, positive, _universal, modal = key
    return ('' if positive else 'not ') + (modal + ' ' if modal else '') + f'{s}::{r}::{o}'


@dataclass(frozen=True)
class NodeView:
    key: Key
    # None is absence of an aggregate, not zero confidence or native abstention.
    confidence: None = None

    def canonical(self):
        return canonical(self.key)


@dataclass(frozen=True)
class DirectRule:
    rule: str
    premises: tuple[Key, ...]
    conclusion: Key
    rule_evidence: tuple[Key, ...] = ()


def direct_rules(keys: set[Key]) -> Iterator[DirectRule]:
    """The five existing formal rule families; no confidence affects discovery."""
    # Ordering below serializes finite sets only. No prefix is admitted as proof.
    rows = sorted(keys)
    positive = [k for k in rows if k[3] and not k[5]]
    declarations = [k for k in rows if k[3] and k[1] == 'has-property'
                    and k[2] == 'transitive' and k[0].startswith('relation:')]
    for a in positive:
        witnesses = [k for k in declarations if k[0] == 'relation:' + a[1]]
        if a[1] != 'implies' and not witnesses:
            continue
        for b in positive:
            if a[1] != b[1] or a[2] != b[0] or a[0] == b[2]:
                continue
            evidence = [()] if a[1] == 'implies' else [(w,) for w in witnesses]
            for witness in evidence:
                yield DirectRule('transitive-composition', (a, b),
                                 (a[0], a[1], b[2], True, False, ''), witness)
    members = [k for k in rows if not k[4] and k[3] and k[1] == 'is' and not k[5]]
    for u in rows:
        if not u[4] or u[1] != 'is' or u[5]:
            continue
        for a in members:
            if a[2] == u[0]:
                rule = 'universal-membership' if u[3] else 'universal-negative-membership'
                yield DirectRule(rule, (a, u), (a[0], 'is', u[2], u[3], False, ''))
    for imp in rows:
        if not imp[3]:
            continue
        if imp[1] == 'implies-proposition':
            # This immutable decoder is used only for its typed identity fields.
            decoded = _from_canonical(imp[2])
            if decoded is not None:
                for antecedent in rows:
                    if canonical(antecedent) == imp[0]:
                        yield DirectRule('structured-modus-ponens', (imp, antecedent),
                                         proposition_key(decoded))
        elif imp[1] == 'implies':
            for truth in rows:
                if truth[3] and truth[1] == 'true' and truth[2] == 'true' and truth[0] == imp[0]:
                    yield DirectRule('modus-ponens', (imp, truth),
                                     (imp[2], 'true', 'true', True, False, ''))


@dataclass
class Ledger:
    keys: tuple[Key, ...]
    premise_keys: tuple[Key, ...]
    sources: dict[str, dict]
    records: tuple[dict, ...]
    closure_complete: bool
    proof_enumeration_complete_for_known: bool
    proof_ledger_complete: bool
    max_conclusion_steps: int
    max_proof_records: int
    conclusion_steps_used: int
    proof_record_lower_bound: int
    blocked_frontier: tuple[Key, ...]
    authority: dict = field(default_factory=lambda: dict(AUTHORITY))

    def to_dict(self):
        return asdict(self)

    def query(self, query):
        """Prototype content view only; never chooses a speech act."""
        if not self.proof_ledger_complete:
            return (), 'prototype-proof-ledger-incomplete'
        rows = list(self.keys)
        targets = [k for k in rows if k[0] == query.subject and k[2] == query.object
                   and _relation_matches(k[1], query.relation)]
        if query.kind == 'why-proposition':
            target_keys = set(targets)
            support = {tuple(k) for r in self.records if tuple(r['conclusion_key']) in target_keys
                       for k in r['premise_keys'] + r['rule_evidence_keys']}
            target_canon = {canonical(k) for k in target_keys}
            support.update(k for k in rows if k[3] and k[1] in {'causes', 'explains'}
                           and k[2] in target_canon)
            selected = [k for k in rows if k in support and k not in target_keys]
        elif query.kind == 'exact-proposition':
            selected = targets
        elif query.kind == 'derive-all':
            selected = [k for k in rows if k not in self.premise_keys]
        elif query.kind == 'relation-from-subject':
            selected = [k for k in rows if k[0] == query.subject and _relation_matches(k[1], query.relation)]
        else:
            raise ValueError('query family outside disposable prototype: ' + query.kind)
        status = ('no-proof-supported-answer' if not selected else 'unique-proof-supported-answer'
                  if len(selected) == 1 else 'multiple-proof-supported-answers-no-forced-choice')
        return tuple(NodeView(k) for k in selected), status

    def legacy_steps(self):
        """Exact numeric projection only when representable; no made-up fallback."""
        if not self.proof_ledger_complete:
            raise ValueError('prototype-proof-ledger-incomplete')
        if len({canonical(k) for k in self.keys}) != len(self.keys):
            raise ValueError('prototype-legacy-canonical-identity-collision')
        if any(r['confidence']['value'] is None for r in self.records):
            raise ValueError('prototype-legacy-scalar-confidence-unrepresentable')
        return tuple(InferenceStep(
            rule=r['rule'], premises=[canonical(tuple(k)) for k in r['premise_keys'] + r['rule_evidence_keys']],
            conclusion=canonical(tuple(r['conclusion_key'])), confidence=r['confidence']['value'],
        ) for r in self.records)

    def audit_query(self, query, provenance, ambiguities=()):
        answers, status = self.query(query)
        try:
            steps = self.legacy_steps()
        except ValueError as exc:
            return {'eligible': (), 'status': str(exc), 'audits': (), 'authority': dict(AUTHORITY)}
        targets = [NodeView(k) for k in self.keys if k[0] == query.subject and k[2] == query.object
                   and _relation_matches(k[1], query.relation)]
        gate = gate_inference_candidates(query_kind=query.kind, candidates=answers,
            provenance_premises=provenance, inference_steps=steps, ambiguities=ambiguities,
            why_targets=targets if query.kind == 'why-proposition' else (),
            block_unscoped_ambiguity=True)
        return {'eligible': tuple(x.canonical() for x in gate.eligible_candidates),
                'status': gate.status, 'audits': gate.audits, 'authority': gate.authority}


def build_ledger(premises, *, max_conclusion_steps=128, max_proof_records=1024):
    """Separate finite budgets, synchronous closure and all-or-incomplete proofs.

    Inputs are already-admitted premise observations. Correction admission is an
    existing upstream/order-sensitive operation, not redefined by this prototype.
    On proof overflow no arbitrarily preferred prefix is exposed. The lower bound
    is cap+1, and the entire proof-dependent consumer view is explicitly ineligible.
    """
    for value in (max_conclusion_steps, max_proof_records):
        if type(value) is not int or value < 0:
            raise ValueError('budgets must be nonnegative integers')
    sources = {}
    original = set()
    for p in premises:
        if 'correction' in p.modifiers:
            raise ValueError('prototype requires already-admitted premises; correction admission is not replaced')
        key = proposition_key(p)
        value = float(p.confidence)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('source confidence must be finite and in [0,1]')
        identity = {'key': key, 'source': p.source, 'source_record_id': p.source_record_id,
                    'source_memory_id': p.source_memory_id,
                    'source_memory_ids': sorted(set(p.source_memory_ids)),
                    'modifiers': sorted(set(p.modifiers)), 'input_derived_flag': p.derived}
        sid = digest(identity)
        if sid not in sources:
            sources[sid] = {'source_id': sid, **identity, 'confidence_readings': []}
        if value not in sources[sid]['confidence_readings']:
            sources[sid]['confidence_readings'].append(value)
        original.add(key)
    for row in sources.values():
        row['confidence_readings'].sort()  # serialization only, never selected
    sources = dict(sorted(sources.items()))
    known = set(original)
    used = 0
    blocked = set()
    while True:
        frontier = {rule.conclusion for rule in direct_rules(known)} - known
        if not frontier:
            break
        if used + len(frontier) > max_conclusion_steps:
            blocked = frontier
            break
        known.update(frontier)
        used += len(frontier)
    closure_complete = not blocked
    node_sources = {k: sorted(sid for sid, s in sources.items() if tuple(s['key']) == k) for k in known}
    records = {}
    overflow = False
    lower_bound = 0
    for rule in direct_rules(known):
        if rule.conclusion not in known:
            continue
        fingerprint_data = {
            'version': 1, 'rule': rule.rule, 'premise_keys': rule.premises,
            'conclusion_key': rule.conclusion, 'rule_evidence_keys': rule.rule_evidence,
            'premise_source_ids': [node_sources[k] for k in rule.premises],
            'rule_evidence_source_ids': [node_sources[k] for k in rule.rule_evidence],
        }
        rid = digest(fingerprint_data)
        if rid in records:
            continue
        lower_bound += 1
        if len(records) == max_proof_records:
            overflow = True
            records.clear()
            break
        records[rid] = {'record_id': rid, **fingerprint_data}
    producer_refs = {k: sorted(rid for rid, r in records.items() if tuple(r['conclusion_key']) == k)
                     for k in known}
    for r in records.values():
        refs, direct_values = [], []
        scalar_representable = True
        for key in r['premise_keys']:
            key = tuple(key)
            observations = [sources[sid] for sid in node_sources[key]]
            values = {v for s in observations for v in s['confidence_readings']}
            refs.append({'key': key, 'source_ids': node_sources[key], 'producer_record_ids': producer_refs[key]})
            if len(values) != 1 or producer_refs[key]:
                scalar_representable = False
            else:
                direct_values.append(next(iter(values)))
        # Preserve the existing conjunction/weakest-premise operation WITHIN ONE
        # route only. Rule-enabling evidence is audited separately as in the model.
        r['confidence'] = {
            'operator': 'existing-within-route-min', 'premise_support_refs': refs,
            'value': min(direct_values) if scalar_representable and direct_values else None,
            'status': 'exact-direct-input-values' if scalar_representable else 'symbolic-unaggregated',
            'cross_route_reducer': None,
        }
    return Ledger(keys=tuple(sorted(known)), premise_keys=tuple(sorted(original)),
        sources=sources, records=tuple(records[k] for k in sorted(records)),
        closure_complete=closure_complete, proof_enumeration_complete_for_known=not overflow,
        proof_ledger_complete=closure_complete and not overflow,
        max_conclusion_steps=max_conclusion_steps, max_proof_records=max_proof_records,
        conclusion_steps_used=used, proof_record_lower_bound=lower_bound,
        blocked_frontier=tuple(sorted(blocked)))
