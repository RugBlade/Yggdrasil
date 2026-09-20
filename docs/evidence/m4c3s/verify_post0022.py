"""M4C3S disposable characterization of exact sealed post0022, never a fix.

Assertions of observed route loss characterize a defect. They do not certify a
correction. Synthetic proof/dependency/consequence fixtures are labelled below;
only the real-ingest checks claim passage through the complete current runtime.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
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
import zipfile

ARTIFACT_SHA = 'b4f45fe3db4af1a019443cae1c563f9e3c371bad04708277fed8e0b1ed6207e0'
SOURCE_SHA = '2d48868a39883be1a19399dc55f9735806b8cfa050d4136757be0d5fed3c05bd'
SOURCE_NAME = 'm4c3r-exact-post0022-published-source.tar.gz'
sha = lambda b: hashlib.sha256(b).hexdigest()


def fingerprint(root):
    return {str(p.relative_to(root)): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--artifact', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    sys.dont_write_bytecode = True
    args.output.mkdir(parents=True, exist_ok=True)
    artifact = args.artifact.read_bytes()
    assert len(artifact) == 679959 and sha(artifact) == ARTIFACT_SHA
    with zipfile.ZipFile(io.BytesIO(artifact)) as z:
        source = z.read(SOURCE_NAME)
        hashes = z.read('m4c3r-published-source-sha256.txt').decode()
    assert sha(source) == SOURCE_SHA
    checks = []
    family_evidence = {}

    def check(name, fn, category='control'):
        try:
            result = fn()
            checks.append(dict(id=name, category=category, status='PASS', evidence=result))
            print('PASS', name, flush=True)
        except Exception:
            checks.append(dict(id=name, category=category, status='FAIL', error=traceback.format_exc()))
            print('FAIL', name, checks[-1]['error'], flush=True)

    with tempfile.TemporaryDirectory(prefix='m4c3s-disposable-') as td:
        td = Path(td)
        root = td/'exact'
        with tarfile.open(fileobj=io.BytesIO(source)) as t:
            t.extractall(root, filter='data')
        before = fingerprint(root)
        assert len(before) == 58
        for line in hashes.splitlines():
            digest, path = line.split(None, 1)
            assert before[path.strip()] == digest
        sys.path.insert(0, str(root/'src'))

        from noeron.cognition import models as cm
        from noeron.conversation_actions import observe_resolution_transition
        from noeron.conversation_premises import ConversationalPremiseEnvelope
        from noeron.conversation_proof import AmbiguityConstraint, audit_proof_support
        from noeron.conversation_resolution import (
            native_current_turn_alternative_sources, resolution_content_units,
            build_operator_resolution_calibration,
        )
        from noeron.conversation_runtime_gate import gate_inference_candidates
        from noeron.development import NativeLanguageFaculty
        from noeron.inference import infer, parse_surface_logic_detailed
        from noeron.language_dialogue import analyze_dialogue_structure
        from noeron.llm import MockLanguageEngine
        from noeron.math import dkt
        from noeron.math.models import LogicalProposition as P, LogicalQuery as Q, MultiMemoryReasoningMathState
        from noeron.memory import LocalEventStore
        from noeron.models import CognitiveEvent, EventKind
        from noeron.orchestrator import Noeron

        for name, module in list(sys.modules.items()):
            if name.startswith('noeron') and getattr(module, '__file__', None):
                assert Path(module.__file__).is_relative_to(root/'src')

        natural = ('If Mira is ready, Mira is calm. If Mira is rested, Mira is calm. '
                   'Mira is ready. Mira is rested. Is Mira calm?')
        prem, query, _ = parse_surface_logic_detailed(natural)
        target = 'mira::is::calm'
        families = {'structured-modus-ponens': (prem, query, target)}
        for name, text in [
            ('universal-membership', 'Every scholar is careful. Every teacher is careful. '
             'Mira is scholar. Mira is teacher. Is Mira careful?'),
            ('universal-negative-membership', 'No scholar is careless. No teacher is careless. '
             'Mira is scholar. Mira is teacher. Is Mira careless?')]:
            pp, qq, _ = parse_surface_logic_detailed(text)
            families[name] = (pp, qq, ('not ' if 'negative' in name else '') +
                              'mira::is::' + ('careless' if 'negative' in name else 'careful'))
        families['modus-ponens'] = ([
            P(subject='a', relation='implies', object='t'), P(subject='b', relation='implies', object='t'),
            P(subject='a', relation='true', object='true'), P(subject='b', relation='true', object='true')],
            Q(kind='exact-proposition', subject='t', relation='true', object='true'), 't::true::true')
        families['transitive-composition'] = ([
            P(subject='a', relation='implies', object='b'), P(subject='a', relation='implies', object='c'),
            P(subject='b', relation='implies', object='d'), P(subject='c', relation='implies', object='d')],
            Q(kind='exact-proposition', subject='a', relation='implies', object='d'), 'a::implies::d')

        def step_key(step):
            return json.dumps({'rule': step.rule, 'premises': step.premises,
                               'conclusion': step.conclusion}, sort_keys=True)

        for name, (pp, qq, goal) in families.items():
            def independent(pp=pp, qq=qq, goal=goal, name=name):
                routes = []
                for indices in ((0, 2), (1, 3)):
                    _, ss, aa, _ = infer([pp[i] for i in indices], qq)
                    matching = [s for s in ss if s.conclusion == goal]
                    assert len(matching) == 1 and goal in [p.canonical() for p in aa]
                    routes.extend(matching)
                assert len({step_key(s) for s in routes}) == 2
                family_evidence[name] = dict(independent_routes=[s.model_dump() for s in routes])
                return family_evidence[name]
            check(name+'_two_routes_independently_proven', independent)

            def combined(pp=pp, qq=qq, goal=goal, name=name):
                routes = set()
                outputs = []
                for order in permutations(pp):
                    dd, ss, aa, status = infer(order, qq)
                    matching = [s for s in ss if s.conclusion == goal]
                    assert len(matching) == 1
                    assert len([d for d in dd if d.canonical() == goal]) == 1
                    assert [a.canonical() for a in aa] == [goal]
                    routes.add(step_key(matching[0]))
                    outputs.append(dict(order=[p.canonical() for p in order],
                                        recorded_route=matching[0].model_dump(), status=status))
                expected = family_evidence[name]['independent_routes']
                assert len(routes) == len(expected) == 2
                family_evidence[name].update(permutations=outputs)
                return {'permutations': len(outputs), 'independent_routes': 2,
                        'recorded_routes_per_permutation': 1, 'distinct_surviving_routes': len(routes),
                        'unique_conclusion_and_answer_preserved': True}
            check(name+'_combined_route_loss', combined, 'defect_reproduction')

        def why_order():
            qq = query.model_copy(update={'kind': 'why-proposition'})
            answers = []
            for order in (prem, list(reversed(prem))):
                _, ss, aa, _ = infer(order, qq)
                answers.append([a.canonical() for a in aa])
                assert target not in answers[-1] and len(ss) == 1
            assert set(answers[0]).isdisjoint(answers[1])
            return {'why_candidates_by_order': answers, 'event_not_its_own_explanation': True}
        check('natural_why_support_depends_on_premise_order', why_order, 'defect_reproduction')

        def envelopes(rows):
            return [ConversationalPremiseEnvelope(canonical=p.canonical(), subject=p.subject,
                relation=p.relation, object=p.object, polarity=p.polarity, source_turn=1,
                origin='current-turn') for p in rows]

        scoped = AmbiguityConstraint(ambiguity_id='controlled-ready-dependency', kind='reference',
                                    affected_canonicals=('mira::is::ready',))
        def gate_order():
            results = []
            for order in (prem, list(reversed(prem))):
                _, ss, aa, _ = infer(order, query)
                g = gate_inference_candidates(query_kind=query.kind, candidates=aa,
                    provenance_premises=envelopes(order), inference_steps=ss, ambiguities=[scoped])
                assert not any(g.authority.values())
                results.append({'status': g.status, 'eligible': [a.canonical() for a in g.eligible_candidates],
                                'audits': g.audits})
            assert [r['status'] for r in results] == [
                'proof-gated-unresolved-ambiguity', 'proof-gate-all-candidates-auditable']
            return {'typed_dependency_fixture_not_parser_claim': True, 'orders': results}
        check('same_scoped_ambiguity_gate_changes_with_route_loss', gate_order, 'defect_reproduction')

        # Independently obtained records, supplied to the unchanged audit only.
        # This is a diagnostic of the consumer, not an edited inference candidate.
        both = infer([prem[0], prem[2]], query)[1] + infer([prem[1], prem[3]], query)[1]
        def conservative_complete_routes():
            a = audit_proof_support(target, premises=envelopes(prem), inference_steps=both,
                                    ambiguities=[scoped])
            b = audit_proof_support(target, premises=envelopes(prem), inference_steps=reversed(both),
                                    ambiguities=[scoped])
            assert a.status == b.status == 'proof-unresolved-ambiguity'
            assert not a.support_gate_passed and not b.support_gate_passed
            return {'status': a.status, 'both_routes_visible': True,
                    'existing_gate_uses_all_recorded_dependencies': True, 'runtime_changed': False}
        check('unchanged_gate_stays_conservative_when_both_records_are_supplied', conservative_complete_routes)

        def proof_inventory():
            r = MultiMemoryReasoningMathState(inference_steps=both)
            rows = native_current_turn_alternative_sources(analyze_dialogue_structure('Explain.'), r)
            proof = [x for x in rows if x.kind == 'proof-alternatives']
            assert len(proof) == 1 and len(proof[0].alternatives) == 2
            assert {json.dumps(json.loads(x), sort_keys=True) for x in proof[0].alternatives} == {step_key(x) for x in both}
            return {'proof_unit_count': 1, 'alternatives': list(proof[0].alternatives),
                    'collector_can_preserve_both_if_upstream_records_exist': True}
        check('typed_proof_inventory_preserves_supplied_distinct_records', proof_inventory)

        def proof_block(kind):
            ep = envelopes(prem)
            kw = {}
            if kind == 'unscoped':
                kw = {'ambiguities': [AmbiguityConstraint(ambiguity_id='unscoped', kind='reference')],
                      'block_unscoped_ambiguity': True}
                expected = 'proof-unresolved-ambiguity'
            elif kind == 'missing':
                ep = [e for e in ep if e.canonical != 'mira::is::ready']
                expected = 'proof-incomplete-provenance'
            else:
                ep = [replace(e, status='conflict', conflict_with=('controlled-conflict',))
                      if e.canonical == 'mira::is::ready' else e for e in ep]
                expected = 'proof-unresolved-conflict'
            a = audit_proof_support(target, premises=ep, inference_steps=both, **kw)
            assert a.status == expected and not a.support_gate_passed
            return {'status': a.status, 'support_gate_passed': False}
        for kind in ('unscoped', 'missing', 'conflict'):
            check('unchanged_proof_gate_blocks_'+kind, lambda kind=kind: proof_block(kind))

        def simple_controls():
            why = query.model_copy(update={'kind': 'why-proposition'})
            goal = P(subject='mira', relation='is', object='calm')
            assert infer([goal], why)[2] == []
            assert len(infer([prem[0], prem[2]], why)[2]) == 2
            assert infer([prem[0], prem[1]], query)[2] == []
            assert len(infer([prem[0], prem[2], prem[0], prem[2]], query)[1]) == 1
            opposite = goal.model_copy(update={'polarity': False})
            aa = infer([goal, opposite], query)[2]
            assert len(aa) == 2 and {p.polarity for p in aa} == {False, True}
            return {'bare_event_is_not_explanation': True, 'single_route_why_supported': True,
                    'missing_antecedents_infer_nothing': True, 'identical_premises_do_not_add_routes': True,
                    'positive_negative_alternatives_preserved': True}
        check('ordinary_logical_and_explanation_controls', simple_controls)

        def no_invented_laws():
            pp = [P(subject='a', relation='left', object='b'), P(subject='b', relation='left', object='c')]
            assert infer(pp, Q(kind='exact-proposition', subject='a', relation='left', object='c'))[2] == []
            uu = P(subject='scholar', relation='is', object='careful', universal=True, modality='may')
            mm = P(subject='mira', relation='is', object='scholar')
            assert infer([uu, mm], Q(kind='exact-proposition', subject='mira', relation='is', object='careful'))[2] == []
            return {'undeclared_transitivity_not_invented': True, 'modal_universal_not_demodalized': True}
        check('formal_rule_boundaries_remain_intact', no_invented_laws)

        def direct_shadow():
            pp = prem + [P(subject='mira', relation='is', object='calm')]
            _, ss, aa, status = infer(pp, query.model_copy(update={'kind': 'why-proposition'}))
            assert ss == [] and aa == []
            return {'independent_routes_available': 2, 'recorded_routes': 0,
                    'why_candidates': [], 'status': status, 'direct_truth_does_not_explain_itself': True}
        check('existing_direct_conclusion_shadows_legitimate_derivations', direct_shadow, 'defect_reproduction')

        def confidence_order():
            pp = [p.model_copy(deep=True) for p in prem]
            pp[0].confidence = .2
            pp[1].confidence = .9
            values = [infer(order, query)[2][0].confidence for order in (pp, list(reversed(pp)))]
            assert values == [.2, .9]
            return {'derived_confidence_by_order': values,
                    'future_fix_must_not_hide_route_confidence_by_authored_ranking': True}
        check('derived_confidence_also_depends_on_first_route', confidence_order, 'defect_reproduction')

        def cycles_and_budget():
            pp = [P(subject='a', relation='implies', object='b'), P(subject='b', relation='implies', object='a'),
                  P(subject='a', relation='true', object='true')]
            dd, ss, _, _ = infer(pp, Q(kind='derive-all'), max_steps=8)
            assert len(ss) <= 8 and len({p.canonical() for p in dd}) == len(dd)
            cap = [P(subject='a', relation='implies', object='b'), P(subject='b', relation='implies', object='c'),
                   P(subject='a', relation='true', object='true')]
            limited = infer(cap, Q(kind='derive-all'), max_steps=1)
            full = infer(cap, Q(kind='derive-all'))
            assert len(limited[1]) == 1 and len(full[1]) > 1
            return {'cycle_steps': [s.model_dump() for s in ss], 'limited_steps': len(limited[1]),
                    'full_steps': len(full[1]), 'limited_result_arity': len(limited),
                    'explicit_completeness_flag_in_infer_return': False,
                    'naive_extra_route_records_would_share_existing_step_budget': True}
        check('finite_cycle_and_derivation_budget_contract_characterized', cycles_and_budget, 'design_constraint')

        runtimes = []
        def real_ingest():
            summaries = []
            for i, clauses in enumerate([
                ['If Mira is ready, Mira is calm.', 'If Mira is rested, Mira is calm.'],
                ['If Mira is rested, Mira is calm.', 'If Mira is ready, Mira is calm.']]):
                text = ' '.join(clauses) + ' Mira is ready. Mira is rested. Why is Mira calm?'
                n = Noeron(MockLanguageEngine(), LocalEventStore(td/f'ingest-{i}.sqlite3'), terra_enabled=False)
                event = CognitiveEvent(kind=EventKind.USER_MESSAGE, source='disposable-owner-fixture',
                    content=text, trusted=True, metadata={'owner_authenticated': True})
                reply = n.ingest(event)
                r = n.state.math_kernel.reasoning
                steps = [s for s in r.inference_steps if s.conclusion == target]
                assert len(steps) == 1 and r.logical_query.kind == 'why-proposition'
                assert reply.speech_act_audit['native_choice_claim'] is False
                assert reply.speech_act_audit['action'] is None
                assert reply.speech_act_audit['content_formation']['ordinary_answer_preserved'] is True
                assert n._hf2_resolution_observation is None
                summaries.append({'input': text, 'steps': [s.model_dump() for s in steps],
                    'answers': [a.canonical() for a in r.answer_candidates],
                    'native_text': reply.native_text,
                    'resolution_selection_status': reply.speech_act_audit['selection_status']})
                runtimes.append((n, event, reply.language_interpretation['structure']))
            assert summaries[0]['answers'] != summaries[1]['answers']
            return {'complete_real_ingest_cases': summaries, 'no_source_monkeypatch': True}
        check('full_real_ingest_reproduces_order_dependent_why_support', real_ingest, 'defect_reproduction')

        def native_choice(target_action=None, tied=False, missing=False):
            n, event, structure = runtimes[0]
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
                        admissible=True,
                        mean_fn=lambda old, new, count: new.model_copy(deep=True) if old is None else
                            dkt.chart_mean([old, new], [count, 1]),
                        source='synthetic-disposable-consequence-fixture-not-live-experience')
                    assert observed['learned'] and observed['speech_act_selection_authority'] is False
            if missing:
                state.action_observations.pop('ask')
            thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='Existing ordinary native content.',
                mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
            audit = n._resolution_speech_act_selection(thought, SimpleNamespace(state=n.state.math_kernel),
                                                     event=event, current_structure=structure)
            if target_action is None or tied or missing:
                assert audit['action'] is None and audit['native_choice_claim'] is False
                assert audit['changes_response_content'] is False
                assert n._hf2_resolution_observation is None
            else:
                assert audit['action'] == target_action and audit['native_choice_claim'] is True
                assert audit['decision_layer'] == 'learned-deliberative'
                if target_action in ('ask', 'clarify'):
                    obs = n._hf2_resolution_observation
                    assert obs is not None
                    snapshot = obs['thought'].model_dump_json()
                    NativeLanguageFaculty().realize(obs['thought'], n.state.cognition.language)
                    assert snapshot == obs['thought'].model_dump_json()
                    for unit in obs['thought'].resolution_content:
                        assert all(v is False for k, v in unit.model_dump().items() if k.endswith('_authority'))
            assert audit['programmed_eligibility_is_choice'] is False
            return {'action': audit['action'], 'native_choice_claim': audit['native_choice_claim'],
                    'status': audit['selection_status'], 'decision_layer': audit['decision_layer'],
                    'synthetic_fixture_not_live_learning': True,
                    'ordinary_response_not_forced_silent_when_resolution_unselected': True}
        check('blank_resolution_geometry_selects_no_act', lambda: native_choice())
        for act in ('clarify', 'ask', 'remain-silent'):
            check('observed_native_geometry_selects_'+act, lambda act=act: native_choice(act))
        check('tied_resolution_geometry_selects_no_act', lambda: native_choice(tied=True))
        check('incomplete_resolution_geometry_selects_no_act', lambda: native_choice('clarify', missing=True))

        def calibration():
            good = build_operator_resolution_calibration(action='ask', authenticated_owner=True,
                        existing_question_candidates=('Why is Mira calm?',))
            bad = build_operator_resolution_calibration(action='ask', authenticated_owner=False,
                        existing_question_candidates=('Why is Mira calm?',))
            assert good.executable and not good.authority['native_choice']
            assert good.origin == 'operator-directed-calibration-not-native-choice'
            assert not bad.executable
            return {'authenticated': good.status, 'unauthenticated': bad.status, 'native_choice': False}
        check('owner_calibration_is_operator_directed_only', calibration)

        after = fingerprint(root)
        check('all_exact_source_bytes_unchanged', lambda: {
            'unchanged': before == after, 'files': len(before), 'python_files': len(hashes.splitlines())}
            if before == after else (_ for _ in ()).throw(AssertionError('Source mutation')))
        (args.output/'source_hashes_before.json').write_text(json.dumps(before, indent=2)+'\n')
        (args.output/'source_hashes_after.json').write_text(json.dumps(after, indent=2)+'\n')

    report = {'milestone': 'M4C3S', 'mode': 'DISPOSABLE_VERIFICATION_ONLY',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'github_source_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
        'artifact_id_used': 10594550960, 'artifact_sha256': ARTIFACT_SHA,
        'source_archive_sha256': SOURCE_SHA, 'source_files': 58, 'python_files': 54,
        'passed': sum(x['status'] == 'PASS' for x in checks), 'failed': sum(x['status'] == 'FAIL' for x in checks),
        'checks': checks, 'rule_family_evidence': family_evidence,
        'runtime_source_changed': False, 'candidate_created': False, 'ordinary_0023_published': False,
        'm4c3r_sealed': True, 'm4c3s_sealed': False, 'stage8b_complete': False,
        'live_runtime_touched': False, 'canonical_db_touched': False, 'certification_claim': False,
        'defect_reproduction_is_not_correction': True,
        'next_decision': 'Separate unique conclusion closure from complete distinct direct proof provenance; resolve finite-budget completeness and per-route confidence contracts before candidate intent. Preserve conservative gates and native-choice boundaries.'}
    (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('milestone', 'passed', 'failed', 'runtime_source_changed', 'candidate_created')}), flush=True)
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
