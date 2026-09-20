"""Verify a disposable two-ledger design against immutable post0022 consumers.

Does not call the completed characterization harness, install an inference
replacement, modify runtime files, or claim a complete runtime correction.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
from itertools import permutations
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import traceback
from types import SimpleNamespace
from uuid import UUID
import zipfile

ARTIFACT_SHA = 'b4f45fe3db4af1a019443cae1c563f9e3c371bad04708277fed8e0b1ed6207e0'
SOURCE_SHA = '2d48868a39883be1a19399dc55f9735806b8cfa050d4136757be0d5fed3c05bd'
sha = lambda b: hashlib.sha256(b).hexdigest()


def fingerprint(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--artifact', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    sys.dont_write_bytecode = True
    args.output.mkdir(parents=True, exist_ok=True)
    blob = args.artifact.read_bytes()
    assert sha(blob) == ARTIFACT_SHA and len(blob) == 679959
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        source = z.read('m4c3r-exact-post0022-published-source.tar.gz')
    assert sha(source) == SOURCE_SHA and len(source) == 663382
    checks = []

    def check(name, fn, category='prototype_contract'):
        try:
            evidence = fn()
            checks.append(dict(id=name, category=category, status='PASS', evidence=evidence))
            print('PASS', name, flush=True)
        except Exception:
            checks.append(dict(id=name, category=category, status='FAIL', error=traceback.format_exc()))
            print('FAIL', name, checks[-1]['error'], flush=True)

    with tempfile.TemporaryDirectory(prefix='m4c3s-two-ledger-') as td0:
        td = Path(td0)
        root = td/'immutable'
        with tarfile.open(fileobj=io.BytesIO(source)) as t:
            t.extractall(root, filter='data')
        before = fingerprint(root)
        assert len(before) == 58
        sys.path.insert(0, str(root/'src'))
        from two_ledger import build_ledger, canonical, digest, NodeView
        from noeron.inference import parse_surface_logic_detailed, proposition_key
        from noeron.math.models import LogicalProposition as P, LogicalQuery as Q, MultiMemoryReasoningMathState
        from noeron.conversation_premises import ConversationalPremiseEnvelope
        from noeron.conversation_proof import AmbiguityConstraint, audit_proof_support
        from noeron.conversation_resolution import (native_current_turn_alternative_sources,
            resolution_content_units, build_operator_resolution_calibration)
        from noeron.language_dialogue import analyze_dialogue_structure, referent_mentions
        from noeron.cognition import models as cm
        from noeron.development import NativeLanguageFaculty
        from noeron.conversation_actions import observe_resolution_transition
        from noeron.math import dkt
        from noeron.llm import MockLanguageEngine
        from noeron.memory import LocalEventStore
        from noeron.models import CognitiveEvent, EventKind
        from noeron.orchestrator import Noeron
        from pydantic import ValidationError

        natural = ('If Mira is ready, Mira is calm. If Mira is rested, Mira is calm. '
                   'Mira is ready. Mira is rested. Why is Mira calm?')
        prem, why, _ = parse_surface_logic_detailed(natural)
        exact = why.model_copy(update={'kind': 'exact-proposition'})
        target = 'mira::is::calm'
        target_key = ('mira', 'is', 'calm', True, False, '')
        families = {'structured-modus-ponens': (prem, target)}
        for name, text, goal in (
            ('universal-membership', 'Every scholar is careful. Every teacher is careful. '
             'Mira is scholar. Mira is teacher.', 'mira::is::careful'),
            ('universal-negative-membership', 'No scholar is careless. No teacher is careless. '
             'Mira is scholar. Mira is teacher.', 'not mira::is::careless')):
            pp, _, _ = parse_surface_logic_detailed(text)
            families[name] = (pp, goal)
        families['modus-ponens'] = ([P(subject='a', relation='implies', object='t'),
            P(subject='b', relation='implies', object='t'), P(subject='a', relation='true', object='true'),
            P(subject='b', relation='true', object='true')], 't::true::true')
        families['transitive-composition'] = ([P(subject='a', relation='implies', object='b'),
            P(subject='a', relation='implies', object='c'), P(subject='b', relation='implies', object='d'),
            P(subject='c', relation='implies', object='d')], 'a::implies::d')

        for name, (pp, goal) in families.items():
            def family(pp=pp, goal=goal, name=name):
                evidence, identities = [], set()
                for order in permutations(pp):
                    ledger = build_ledger(order)
                    rr = [r for r in ledger.records if canonical(r['conclusion_key']) == goal]
                    assert ledger.proof_ledger_complete and len(rr) == 2
                    assert sum(canonical(k) == goal for k in ledger.keys) == 1
                    assert all(r['rule'] == name for r in rr)
                    identities.add(digest(ledger.to_dict()))
                    evidence.append([r['record_id'] for r in rr])
                assert len(identities) == 1
                return {'permutations': len(evidence), 'routes_per_target': 2,
                        'distinct_full_ledger_serializations': len(identities),
                        'example': build_ledger(pp).to_dict()}
            check(name+'_route_complete_order_independent', family)

        full = build_ledger(prem)
        def why_complete():
            answers, status = full.query(why)
            expected = {p.canonical() for p in prem}
            assert {p.canonical() for p in answers} == expected
            assert target not in expected and len(answers) == 4
            return {'candidates': sorted(expected), 'status': status, 'no_speech_act_selected': True}
        check('why_support_contains_both_direct_routes', why_complete)

        def direct_target():
            rows = [*prem, P(subject='mira', relation='is', object='calm', source_record_id='direct-target')]
            ledgers = [build_ledger(order) for order in (rows, list(reversed(rows)))]
            for ledger in ledgers:
                assert ledger.conclusion_steps_used == 0
                assert len(ledger.records) == 2 and ledger.proof_ledger_complete
                assert {a.canonical() for a in ledger.query(why)[0]} == {p.canonical() for p in prem}
            assert ledgers[0].to_dict() == ledgers[1].to_dict()
            return ledgers[0].to_dict()
        check('direct_target_does_not_shadow_derivations', direct_target)

        def envelopes(rows):
            return [ConversationalPremiseEnvelope(canonical=p.canonical(), subject=p.subject,
                relation=p.relation, object=p.object, polarity=p.polarity, source_turn=1,
                origin='current-turn', confidence=p.confidence) for p in rows]

        def bare_event():
            p = P(subject='mira', relation='is', object='calm')
            ledger = build_ledger([p])
            assert ledger.query(why)[0] == () and ledger.records == ()
            audit = audit_proof_support(p.canonical(), premises=envelopes([p]), require_explanation=True)
            assert not audit.support_gate_passed and audit.status == 'explanation-missing-causal-support'
            return {'query_status': ledger.query(why)[1], 'unchanged_audit_status': audit.status}
        check('bare_event_truth_is_not_explanation', bare_event)

        def duplicates():
            doubled = build_ledger([*prem, *prem, prem[0].model_copy(deep=True)])
            assert doubled.to_dict() == full.to_dict()
            return {'sources': len(doubled.sources), 'proof_records': len(doubled.records)}
        check('identical_premise_duplicates_do_not_multiply_routes', duplicates)

        def parallel_sources():
            a = prem[2].model_copy(update={'source_record_id': 'observed-A', 'confidence': .2})
            b = prem[2].model_copy(update={'source_record_id': 'observed-B', 'confidence': .9})
            ledger = build_ledger([prem[0], a, b])
            assert len(ledger.records) == 1
            record = ledger.records[0]
            assert len(record['premise_source_ids'][1]) == 2
            assert record['confidence']['value'] is None
            assert {s['confidence_readings'][0] for s in ledger.sources.values()
                    if s['source_record_id'] in {'observed-A', 'observed-B'}} == {.2, .9}
            return ledger.to_dict()
        check('parallel_source_provenance_preserved_without_fake_rule_multiplicity', parallel_sources)

        def same_source_readings():
            a = prem[2].model_copy(update={'confidence': .2})
            b = prem[2].model_copy(update={'confidence': .9})
            l = build_ledger([prem[0], a, b])
            r = l.records[0]
            assert len(r['premise_source_ids'][1]) == 1
            assert l.sources[r['premise_source_ids'][1][0]]['confidence_readings'] == [.2, .9]
            assert r['confidence']['value'] is None
            return l.to_dict()
        check('same_source_different_confidence_readings_retained', same_source_readings)

        cycle = [P(subject='a', relation='implies', object='b'),
                 P(subject='b', relation='implies', object='a'),
                 P(subject='a', relation='true', object='true')]
        def cycles():
            l = build_ledger(cycle)
            assert l.proof_ledger_complete and len(l.records) == 2
            assert len(l.keys) == 4 and l.conclusion_steps_used == 1
            assert l.to_dict() == build_ledger(cycle * 5).to_dict()
            ids = {r['record_id'] for r in l.records}
            for r in l.records:
                assert r['confidence']['value'] is None
                for ref in r['confidence']['premise_support_refs']:
                    assert set(ref['producer_record_ids']) <= ids
            return l.to_dict()
        check('cycles_use_finite_direct_records_and_symbolic_references', cycles)

        def separate_budgets():
            l = build_ledger(prem, max_conclusion_steps=1, max_proof_records=2)
            assert l.proof_ledger_complete and l.conclusion_steps_used == 1 and len(l.records) == 2
            return l.to_dict()
        check('one_conclusion_budget_still_collects_both_routes', separate_budgets)

        def proof_overflow():
            l = build_ledger(prem, max_conclusion_steps=1, max_proof_records=1)
            assert l.keys == full.keys and l.closure_complete
            assert not l.proof_ledger_complete and not l.proof_enumeration_complete_for_known
            assert l.records == () and l.proof_record_lower_bound == 2
            assert l.query(why)[0] == ()
            result = l.audit_query(exact, envelopes(prem))
            assert not result['eligible'] and result['status'] == 'prototype-proof-ledger-incomplete'
            return {'ledger': l.to_dict(), 'consumer': result}
        check('tiny_proof_budget_marks_incomplete_without_preferred_prefix', proof_overflow)

        def frontier_budget():
            rows = [P(subject='a', relation='implies', object='b'),
                    P(subject='a', relation='implies', object='c'),
                    P(subject='a', relation='true', object='true')]
            identities = set()
            for order in permutations(rows):
                l = build_ledger(order, max_conclusion_steps=1)
                assert not l.closure_complete and not l.proof_ledger_complete
                assert l.conclusion_steps_used == 0 and len(l.blocked_frontier) == 2
                identities.add(digest(l.to_dict()))
            assert len(identities) == 1
            complete = build_ledger(rows, max_conclusion_steps=2)
            assert complete.proof_ledger_complete and complete.conclusion_steps_used == 2
            return {'incomplete': l.to_dict(), 'larger_budget': complete.to_dict()}
        check('small_conclusion_budget_withholds_whole_frontier_order_independently', frontier_budget)

        def zero_budgets():
            none = build_ledger([], max_conclusion_steps=0, max_proof_records=0)
            assert none.proof_ledger_complete
            constrained = build_ledger(prem, max_conclusion_steps=0, max_proof_records=0)
            assert not constrained.closure_complete and not constrained.proof_ledger_complete
            no_records = build_ledger(prem, max_conclusion_steps=1, max_proof_records=0)
            assert no_records.closure_complete and not no_records.proof_ledger_complete
            return {'empty_is_complete': True, 'nonempty_frontier_is_explicitly_incomplete': True,
                    'zero_proof_cap_does_not_change_closure': no_records.keys == full.keys}
        check('zero_budgets_have_explicit_finite_semantics', zero_budgets)

        def confidence_permutations():
            rows = [p.model_copy(deep=True) for p in prem]
            rows[0].confidence = rows[2].confidence = .2
            rows[1].confidence = rows[3].confidence = .9
            identities = set()
            for order in permutations(rows):
                l = build_ledger(order)
                assert sorted(r['confidence']['value'] for r in l.records) == [.2, .9]
                assert all(r['confidence']['cross_route_reducer'] is None for r in l.records)
                assert l.query(exact)[0][0].confidence is None
                identities.add(digest(l.to_dict()))
            assert len(identities) == 1
            return {'permutations': 24, 'route_values': [.2, .9],
                    'conclusion_aggregate': None, 'ledger': l.to_dict()}
        check('confidence_02_09_permutations_preserve_both_without_reducer', confidence_permutations)

        def zero_confidence():
            rows = [p.model_copy(update={'confidence': 0.0}) for p in prem]
            l = build_ledger(rows)
            assert all(r['confidence']['value'] == 0.0 for r in l.records)
            assert all(s.confidence == 0.0 for s in l.legacy_steps())
            return {'route_confidence_values': [r['confidence']['value'] for r in l.records],
                    'zero_not_replaced_by_default': True}
        check('zero_route_confidence_is_preserved', zero_confidence)

        def nested_confidence():
            rows = [*prem, P(subject=target, relation='implies-proposition', object='mira::is::safe')]
            l = build_ledger(rows)
            safe = [r for r in l.records if canonical(r['conclusion_key']) == 'mira::is::safe']
            assert len(safe) == 1 and safe[0]['confidence']['value'] is None
            ref = safe[0]['confidence']['premise_support_refs'][1]
            assert len(ref['producer_record_ids']) == 2
            assert l.proof_ledger_complete
            assert l.audit_query(exact, envelopes(rows))['status'] == 'prototype-legacy-scalar-confidence-unrepresentable'
            return {'ledger': l.to_dict(), 'legacy_adapter': 'explicitly unrepresentable; no invented scalar'}
        check('chained_confidence_preserves_support_graph_without_path_expansion', nested_confidence)

        scoped = AmbiguityConstraint(ambiguity_id='typed-ready-source', kind='reference',
                                    affected_canonicals=('mira::is::ready',), alternatives=('mira', 'sara'))
        def consumer(kind):
            ep = envelopes(prem)
            ambiguities = []
            if kind == 'scoped':
                ambiguities = [scoped]; expected = 'proof-gated-unresolved-ambiguity'
            elif kind == 'unscoped':
                ambiguities = [AmbiguityConstraint(ambiguity_id='unscoped', kind='reference')]
                expected = 'proof-gated-unresolved-ambiguity'
            elif kind == 'missing':
                ep = [e for e in ep if e.canonical != 'mira::is::ready']
                expected = 'proof-gated-incomplete-provenance'
            elif kind == 'conflict':
                ep = [replace(e, status='conflict', conflict_with=('explicit-conflict',))
                      if e.canonical == 'mira::is::ready' else e for e in ep]
                expected = 'proof-gated-unresolved-conflict'
            else:
                expected = 'proof-gate-all-candidates-auditable'
            result = full.audit_query(exact, ep, ambiguities)
            assert result['status'] == expected
            assert bool(result['eligible']) == (kind == 'clean')
            assert not any(result['authority'].values())
            for audit in result['audits']:
                assert not any(audit['authority'].values())
            return result
        for kind in ('scoped', 'unscoped', 'missing', 'conflict', 'clean'):
            check('unchanged_proof_consumer_'+kind, lambda kind=kind: consumer(kind), 'consumer_control')

        def why_audit():
            clean = full.audit_query(why, envelopes(prem))
            blocked = full.audit_query(why, envelopes(prem), [scoped])
            assert len(clean['eligible']) == 4 and not blocked['eligible']
            assert blocked['status'] == 'proof-gated-unresolved-ambiguity'
            return {'clean': clean, 'scoped_ambiguity': blocked,
                    'scoped_ambiguity_is_explicit_fixture_not_parser_claim': True}
        check('why_support_is_complete_and_all_route_ambiguity_remains_blocked', why_audit, 'consumer_control')

        def alternatives():
            query = Q(kind='relation-from-subject', subject='mira', relation='is')
            l = build_ledger([P(subject='mira', relation='is', object='scholar'),
                              P(subject='mira', relation='is', object='teacher')])
            aa, status = l.query(query)
            assert {a.canonical() for a in aa} == {'mira::is::scholar', 'mira::is::teacher'}
            assert status == 'multiple-proof-supported-answers-no-forced-choice'
            return {'alternatives': [a.canonical() for a in aa], 'status': status}
        check('genuine_proposition_alternatives_remain_unranked', alternatives)

        def proof_inventory():
            reasoning = MultiMemoryReasoningMathState(inference_steps=list(full.legacy_steps()))
            rows = native_current_turn_alternative_sources(analyze_dialogue_structure('Explain.'), reasoning)
            proof = [r for r in rows if r.kind == 'proof-alternatives']
            assert len(proof) == 1 and len(proof[0].alternatives) == 2 and proof[0].act == ''
            return {'alternatives': proof[0].alternatives, 'compatible_actions': proof[0].compatible_actions,
                    'act': proof[0].act}
        check('prototype_routes_reach_unchanged_act_neutral_inventory', proof_inventory, 'consumer_control')

        event = CognitiveEvent(id=UUID('00000000-0000-0000-0000-000000000053'),
            kind=EventKind.USER_MESSAGE, source='disposable-prototype-owner-fixture', content=natural,
            trusted=True, metadata={'owner_authenticated': True})
        n = Noeron(MockLanguageEngine(), LocalEventStore(td/'prototype-fixture.sqlite3'), terra_enabled=False)
        n.state.last_event_id = event.id
        n.state.math_kernel.reasoning = MultiMemoryReasoningMathState(
            logical_query=why, inference_steps=list(full.legacy_steps()), answer_candidates=list(prem),
            answer_selection_status='multiple-proof-supported-answers-no-forced-choice')
        structure = analyze_dialogue_structure(natural)

        def native_choice(target_action=None, tied=False, missing=False):
            state = n.state.cognition.speech_act_development
            context = n.state.math_kernel.dkt.core_knot
            state.action_pre_knots = {}; state.action_post_knots = {}; state.action_observations = {}
            state.transition_observations = 0
            if target_action is not None or tied:
                for i, act in enumerate(('clarify', 'ask', 'defer', 'remain-silent'), 1):
                    pre = context.model_copy(deep=True)
                    if not tied and act != target_action:
                        pre.c0[0] += i*.2
                    pre.invariant_signature = dkt.invariant_signature(pre)
                    observed = observe_resolution_transition(state, act, pre, context.model_copy(deep=True),
                        admissible=True, mean_fn=lambda old, new, count: new.model_copy(deep=True) if old is None
                        else dkt.chart_mean([old, new], [count, 1]), source='synthetic-prototype-consequence-fixture')
                    assert observed['learned'] and not observed['speech_act_selection_authority']
            if missing:
                state.action_observations.pop('ask')
            thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='Existing ordinary content.',
                mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
            audit = n._resolution_speech_act_selection(thought, SimpleNamespace(state=n.state.math_kernel),
                event=event, current_structure=structure)
            if target_action is None or tied or missing:
                assert audit['action'] is None and not audit['native_choice_claim']
                assert not audit['changes_response_content']
                assert n._hf2_resolution_observation is None
            else:
                assert audit['action'] == target_action and audit['native_choice_claim']
                assert audit['decision_layer'] == 'learned-deliberative'
                if target_action in ('clarify', 'ask'):
                    thought = n._hf2_resolution_observation['thought']
                    proofs = [u for u in thought.resolution_content if u.kind == 'proof-alternatives']
                    assert len(proofs) == 1 and len(proofs[0].alternatives) == 2
                    for u in thought.resolution_content:
                        assert all(v is False for k, v in u.model_dump().items() if k.endswith('_authority'))
            assert not audit['programmed_eligibility_is_choice']
            return {'action': audit['action'], 'native_choice_claim': audit['native_choice_claim'],
                    'status': audit['selection_status'], 'decision_layer': audit['decision_layer'],
                    'fixture_scope': 'new prototype records supplied to unchanged runtime consumer; no infer replacement'}
        check('new_proof_inventory_blank_geometry_selects_no_act', lambda: native_choice(), 'native_control')
        for act in ('clarify', 'ask', 'remain-silent'):
            check('new_proof_inventory_observed_geometry_'+act, lambda act=act: native_choice(act), 'native_control')
        check('new_proof_inventory_tied_geometry_selects_no_act', lambda: native_choice(tied=True), 'native_control')
        check('new_proof_inventory_incomplete_geometry_selects_no_act',
              lambda: native_choice('clarify', missing=True), 'native_control')

        def calibration():
            plan = build_operator_resolution_calibration(action='ask', authenticated_owner=True,
                existing_question_candidates=('Why is Mira calm?',))
            denied = build_operator_resolution_calibration(action='ask', authenticated_owner=False,
                existing_question_candidates=('Why is Mira calm?',))
            assert plan.executable and not denied.executable
            assert plan.origin == 'operator-directed-calibration-not-native-choice'
            assert not plan.authority['native_choice']
            return {'origin': plan.origin, 'authority': plan.authority}
        check('owner_calibration_remains_operator_directed', calibration, 'native_control')

        def sealed_surface():
            structure = analyze_dialogue_structure('Did she leave?',
                recent_referents=referent_mentions(analyze_dialogue_structure('Mira met Sara.')))
            r = MultiMemoryReasoningMathState(inference_steps=list(full.legacy_steps()))
            rows = native_current_turn_alternative_sources(structure, r)
            units = resolution_content_units(rows, action='clarify', source_event_id=event.id)
            thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='', resolution_content=units,
                mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
            snapshot = thought.model_dump_json()
            u = NativeLanguageFaculty().realize(thought, cm.LanguageFacultyState())
            assert thought.model_dump_json() == snapshot
            assert len(units) == 3 and len(u.utterance_plan) == 2
            assert u.utterance_plan[0] == 'she: sara / mira?'
            assert 'Did she leave?:' not in u.native_text
            assert all(x in u.native_text for x in rows[-1].alternatives)
            return {'typed_units': len(units), 'surface_clauses': len(u.utterance_plan),
                    'reference_clause': u.utterance_plan[0], 'proof_alternatives_preserved': True}
        check('sealed_0022_correspondence_with_new_proof_inventory_unchanged', sealed_surface, 'consumer_control')

        def declared_transitivity():
            rows = [P(subject='a', relation='touches', object='b'), P(subject='b', relation='touches', object='c')]
            assert not build_ledger(rows).records
            declaration = P(subject='relation:touches', relation='has-property', object='transitive', source_record_id='formal-declaration')
            l = build_ledger([*rows, declaration])
            assert len(l.records) == 1 and len(l.records[0]['rule_evidence_keys']) == 1
            result = l.audit_query(Q(kind='exact-proposition', subject='a', relation='touches', object='c'), envelopes(rows))
            assert result['status'] == 'proof-gated-incomplete-provenance'
            return {'ledger': l.to_dict(), 'absent_declaration_provenance': result}
        check('explicit_transitive_rule_enablement_is_retained_as_provenance', declared_transitivity)

        def typed_identity():
            p = P(subject='scholar', relation='is', object='careful')
            u = p.model_copy(update={'universal': True})
            l = build_ledger([p, u])
            assert len(l.keys) == 2 and canonical(l.keys[0]) == canonical(l.keys[1])
            result = l.audit_query(Q(kind='exact-proposition', subject='scholar', relation='is', object='careful'), envelopes([p,u]))
            assert result['status'] == 'prototype-legacy-canonical-identity-collision'
            return {'typed_keys': l.keys, 'legacy_adapter_status': result['status']}
        check('typed_identity_collision_is_not_silently_collapsed', typed_identity, 'compatibility_boundary')

        def scalar_boundary():
            node = full.query(exact)[0][0]
            assert node.confidence is None
            errors = []
            for name, constructor in [('LogicalProposition', lambda: P(subject='mira', relation='is', object='calm', confidence=node.confidence)),
                ('NativeProposition', lambda: cm.NativeProposition(subject='mira', relation='is', object='calm', confidence=node.confidence)),
                ('MultiMemoryReasoningMathState', lambda: MultiMemoryReasoningMathState(confidence=node.confidence))]:
                try:
                    constructor()
                except ValidationError as exc:
                    errors.append({'model': name, 'error_types': [e['type'] for e in exc.errors()]})
                else:
                    raise AssertionError('expected scalar-model incompatibility: ' + name)
            assert len(errors) == 3
            return {'expected_rejections': errors, 'scope_frozen': False,
                    'no_scalar_imputed': True, 'candidate_authorized': False}
        check('existing_runtime_models_require_scalar_confidence', scalar_boundary, 'compatibility_boundary')

        def admission_boundary():
            p = prem[2].model_copy(update={'modifiers': ['correction']})
            try:
                build_ledger([p])
            except ValueError as exc:
                assert 'already-admitted' in str(exc)
                return {'status': str(exc), 'existing_correction_admission_not_redefined': True}
            raise AssertionError('prototype silently reinterpreted correction')
        check('correction_admission_boundary_is_explicit', admission_boundary, 'compatibility_boundary')

        def authority():
            assert not any(full.authority.values())
            assert all(r['confidence']['cross_route_reducer'] is None for r in full.records)
            assert 'speech_act' not in full.to_dict() and 'selected_answer' not in full.to_dict()
            return {'authority': full.authority, 'speech_act_selection_field': False, 'answer_selection_field': False}
        check('all_prototype_authorities_false', authority)

        def source_unchanged():
            after = fingerprint(root)
            assert before == after
            imported = []
            for name, module in sorted(sys.modules.items()):
                if name.startswith('noeron') and getattr(module, '__file__', None):
                    assert Path(module.__file__).is_relative_to(root/'src')
                    imported.append(name)
            return {'files': len(after), 'python_files': sum(k.endswith('.py') for k in after),
                    'imported_modules': imported, 'all_bytes_unchanged': True}
        check('immutable_source_and_consumer_imports_verified', source_unchanged)
        (args.output/'source_hashes_before.json').write_text(json.dumps(before, indent=2)+'\n')
        (args.output/'source_hashes_after.json').write_text(json.dumps(fingerprint(root), indent=2)+'\n')

    report = {'schema':'M4C3S-DISPOSABLE-TWO-LEDGER-DESIGN-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
        'artifact_id_used':10594550960, 'artifact_sha256':ARTIFACT_SHA, 'source_archive_sha256':SOURCE_SHA,
        'passed':sum(c['status']=='PASS' for c in checks), 'failed':sum(c['status']=='FAIL' for c in checks),
        'checks':checks, 'formal_family_permutations':120, 'confidence_permutations':24,
        'completed_previous_verification_rerun':False, 'runtime_source_changed':False,
        'full_runtime_integration_tested':False, 'candidate_created':False, 'ordinary_0023_published':False,
        'm4c3r_sealed':True, 'm4c3s_sealed':False, 'stage8b_complete':False,
        'live_runtime_touched':False, 'canonical_db_touched':False, 'certification_claim':False,
        'design_contract_status':'PROTOTYPE_PROVEN_RUNTIME_COMPATIBILITY_SCOPE_NOT_FROZEN',
        'candidate_authorized':False,
        'next_action':'Resolve and test confidence-preserving runtime compatibility across scalar models/consumers, typed-key audit projection and existing correction admission before freezing the exact candidate file set. No aggregate confidence or native action policy is authorized.'}
    (args.output/'prototype_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','failed','candidate_created','candidate_authorized')}), flush=True)
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
