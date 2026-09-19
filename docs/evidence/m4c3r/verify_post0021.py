"""Disposable M4C3R characterization; imports only the sealed post0021 artifact.

No candidate, monkey patch, source edit, historical gate rerun, or live DB access.
Synthetic consequence fixtures exercise the native selector; they are not claims
about the live individual's learning history. Expected duplicates are findings,
not passing assertions that the defect has been corrected.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import traceback
from types import SimpleNamespace
from uuid import uuid4
import zipfile

ARTIFACT_SHA256 = '996ac91d1b6bcdedc6c2eb711908817e1b1dd6b89621bbc98ed227c984a98f9f'
SOURCE_SHA256 = 'cdc054a9af9f941f90b82eb5df814c54471203aa486cfea0aeb3e3348ca52d0d'
SOURCE_NAME = 'm4c3q-exact-post0021-published-source.tar.gz'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(root):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    data = args.artifact.read_bytes()
    assert len(data) == 677959 and digest(data) == ARTIFACT_SHA256
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    details = {}

    def check(name, function, category='control'):
        try:
            evidence = function()
            results.append(dict(id=name, category=category, status='PASS', evidence=evidence))
            print('PASS', name, flush=True)
        except Exception:
            results.append(dict(id=name, category=category, status='FAIL', error=traceback.format_exc()))
            print('FAIL', name, results[-1]['error'], flush=True)

    with tempfile.TemporaryDirectory(prefix='m4c3r-disposable-') as scratch:
        scratch = Path(scratch)
        with zipfile.ZipFile(args.artifact) as z:
            source = z.read(SOURCE_NAME)
            published_hashes = z.read('m4c3q-published-source-sha256.txt').decode()
        assert digest(source) == SOURCE_SHA256
        archive = scratch / SOURCE_NAME
        archive.write_bytes(source)
        root = scratch / 'exact'
        with tarfile.open(archive) as t:
            t.extractall(root, filter='data')
        before = fingerprint(root)
        for line in published_hashes.splitlines():
            sha, path = line.split(None, 1)
            assert before[path.strip()] == sha
        sys.path.insert(0, str(root / 'src'))

        from noeron.cognition import models as cm
        from noeron.conversation_actions import observe_resolution_transition
        from noeron.conversation_resolution import (
            native_current_turn_alternative_sources, resolution_content_units,
            build_operator_resolution_calibration,
        )
        from noeron.development import NativeLanguageFaculty
        from noeron.language_dialogue import analyze_dialogue_structure, referent_mentions
        from noeron.llm import MockLanguageEngine
        from noeron.math import dkt
        from noeron.math.models import (
            LogicalProposition, LogicalQuery, MultiMemoryReasoningMathState, InferenceStep,
        )
        from noeron.memory import LocalEventStore
        from noeron.models import CognitiveEvent, EventKind
        from noeron.orchestrator import Noeron

        for name, module in list(sys.modules.items()):
            if name.startswith('noeron') and getattr(module, '__file__', None):
                assert Path(module.__file__).is_relative_to(root / 'src')

        recent = referent_mentions(analyze_dialogue_structure('Mira met Sara.'))

        def structure(text):
            return analyze_dialogue_structure(text, recent_referents=recent)

        ref_rows = native_current_turn_alternative_sources(structure('Did she leave?'))
        event_rows = native_current_turn_alternative_sources(structure('Did Mira give Omar the book?'))
        event_id = uuid4()

        def render(rows, action='clarify', explicit_units=None):
            units = (resolution_content_units(rows, action=action, source_event_id=event_id)
                     if explicit_units is None else explicit_units)
            thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='',
                resolution_content=units,
                mathematical_provenance=cm.MathematicalProvenance(source_event_id=event_id))
            snapshot = thought.model_dump_json()
            utterance = NativeLanguageFaculty().realize(thought, cm.LanguageFacultyState())
            assert snapshot == thought.model_dump_json(), 'Realization changed the typed inventory'
            for unit in units:
                assert unit.unresolved is True
                assert all(value is False for key, value in unit.model_dump().items()
                           if key.endswith('_authority'))
            return utterance, units

        def owner(text):
            return CognitiveEvent(kind=EventKind.USER_MESSAGE, source='disposable-owner-fixture',
                content=text, trusted=True, metadata={'owner_authenticated': True})

        runtime = Noeron(MockLanguageEngine(), LocalEventStore(scratch / 'reference.sqlite3'),
                         terra_enabled=False)
        runtime.ingest(owner('Mira met Sara.'))
        current = owner('Did she leave?')
        reply = runtime.ingest(current)
        current_structure = reply.language_interpretation['structure']
        thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='',
            mathematical_provenance=cm.MathematicalProvenance(source_event_id=current.id))

        def seed(target=None, tied=False):
            st = runtime.state.cognition.speech_act_development
            st.action_pre_knots = {}; st.action_post_knots = {}; st.action_observations = {}
            st.transition_observations = 0
            context = runtime.state.math_kernel.dkt.core_knot
            for index, action in enumerate(('clarify', 'ask', 'defer', 'remain-silent'), 1):
                pre = context.model_copy(deep=True)
                if not tied and action != target:
                    pre.c0[0] += index * .2
                pre.invariant_signature = dkt.invariant_signature(pre)
                result = observe_resolution_transition(st, action, pre, context.model_copy(deep=True),
                    admissible=True,
                    mean_fn=lambda old, new, count: new.model_copy(deep=True) if old is None else
                        dkt.chart_mean([old, new], [count, 1]),
                    source='synthetic-disposable-consequence-fixture-not-live-experience')
                assert result['learned'] and result['speech_act_selection_authority'] is False

        def select():
            return runtime._resolution_speech_act_selection(thought,
                SimpleNamespace(state=runtime.state.math_kernel),
                event=current, current_structure=current_structure)

        def audit_summary(audit):
            return {k: audit.get(k) for k in (
                'action', 'native_choice_claim', 'selection_status', 'decision_layer',
                'candidate_distances', 'selection_basis', 'native_context_source',
                'changes_outward_transport', 'authority', 'content_formation')}

        def blank():
            audit = reply.speech_act_audit
            assert reply.native_text == '' and audit['action'] is None
            assert audit['native_choice_claim'] is False
            assert audit['selection_status'] == 'unresolved-insufficient-speech-act-consequence-geometry'
            assert runtime._hf2_resolution_observation is None
            for key in ('semantic_truth_authority', 'answer_authority', 'speech_act_selection_authority'):
                assert current_structure[key] is False
            return audit_summary(audit)
        check('01_blank_geometry_silent', blank)

        def native_clarify():
            seed('clarify'); audit = select()
            assert audit['action'] == 'clarify' and audit['native_choice_claim'] is True
            assert audit['decision_layer'] == 'learned-deliberative'
            assert audit['programmed_eligibility_is_choice'] is False
            assert audit['content_formation']['alternative_inventory_choice_authority'] is False
            observed = runtime._hf2_resolution_observation['thought']
            assert len(observed.resolution_content) == 2
            assert observed.native_utterance.native_text == 'she: sara / mira? Did she leave?: sara / mira?'
            details['native_clarify'] = audit_summary(audit)
            return dict(audit=audit_summary(audit), surface=observed.native_utterance.native_text)
        check('02_native_clarify_from_consequence_fixture', native_clarify)

        def reference_duplicate():
            assert [r.kind for r in ref_rows] == ['reference-alternatives', 'qud-alternatives']
            primary, derivative = ref_rows
            assert 'unresolved-source:' + primary.source_id in derivative.source_units
            assert derivative.alternatives == primary.alternatives == ('sara', 'mira')
            u, units = render(ref_rows)
            assert u.utterance_plan == ['she: sara / mira?', 'Did she leave?: sara / mira?']
            return dict(surface=u.native_text, units=[x.model_dump(mode='json') for x in units],
                        desired_one_clause_per_unresolved_source=False, duplicate_reproduced=True)
        check('03_reference_derivative_duplicate_reproduced', reference_duplicate, 'defect-reproduction')

        def event_duplicate():
            primary = [r for r in event_rows if r.kind == 'event-role-alternatives']
            derivative = [r for r in event_rows if r.kind == 'qud-alternatives']
            assert len(primary) == len(derivative) == 2
            for p, q in zip(primary, derivative):
                assert 'unresolved-source:' + p.source_id in q.source_units
                assert q.alternatives == p.alternatives
                u, _ = render((p, q)); assert len(u.utterance_plan) == 2
            u, _ = render(event_rows); assert len(u.utterance_plan) == 4
            return dict(surface=u.native_text, sources=[asdict(r) for r in event_rows],
                        desired_one_clause_per_unresolved_source=False, duplicate_reproduced=True)
        check('04_event_role_derivative_duplicate_reproduced', event_duplicate, 'defect-reproduction')

        def independent_references():
            rows = native_current_turn_alternative_sources(structure('Did she leave? Did she stay?'))
            primary = [r for r in rows if r.kind == 'reference-alternatives']
            assert len(primary) == 2 and primary[0].source_id != primary[1].source_id
            assert primary[0].focus_surface == primary[1].focus_surface == 'she'
            assert primary[0].alternatives == primary[1].alternatives
            u, units = render(rows)
            assert len(units) == len(u.utterance_plan) == 4
            assert u.utterance_plan.count('she: sara / mira?') == 2
            return dict(surface=u.native_text, independent_source_ids=[p.source_id for p in primary],
                        primary_clauses=2, derivative_clauses=2)
        check('05_two_independent_references_identical_wording', independent_references)

        def qud_without_primary():
            q = ref_rows[1]
            for action in ('clarify', 'ask'):
                u, units = render([q], action)
                assert len(units) == 1 and u.native_text == 'Did she leave?: sara / mira?'
            return dict(surface=u.native_text, primary_absent=True, actions=['clarify', 'ask'])
        check('06_qud_without_matching_primary_surfaces', qud_without_primary)

        reasoning = MultiMemoryReasoningMathState(
            logical_query=LogicalQuery(kind='relation-from-subject', raw='What is Mira?'),
            answer_candidates=[LogicalProposition(subject='mira', relation='is', object=o)
                               for o in ('scholar', 'teacher')],
            answer_selection_status='multiple-proof-supported-answers-no-forced-choice',
            inference_steps=[InferenceStep(rule='r1', premises=['a::true::true'], conclusion='b::true::true'),
                             InferenceStep(rule='r2', premises=['c::true::true'], conclusion='b::true::true')])
        reason_rows = native_current_turn_alternative_sources(analyze_dialogue_structure('What is Mira?'), reasoning)

        def typed_reasoning(kind):
            rows = [r for r in reason_rows if r.kind == kind]; assert len(rows) == 1
            for action in ('clarify', 'ask'):
                u, units = render(rows, action)
                assert len(u.utterance_plan) == 1 and len(units[0].alternatives) == 2
                assert all(x in u.native_text for x in rows[0].alternatives)
                assert tuple(units[0].alternatives) == rows[0].alternatives
            if kind == 'proof-alternatives':
                assert [json.loads(x)['rule'] for x in rows[0].alternatives] == ['r1', 'r2']
            else:
                assert rows[0].alternatives == ('mira::is::scholar', 'mira::is::teacher')
            return dict(kind=kind, alternatives=list(rows[0].alternatives), surface=u.native_text)
        check('07_proposition_alternatives_untouched', lambda: typed_reasoning('proposition-alternatives'))
        check('08_proof_alternatives_untouched', lambda: typed_reasoning('proof-alternatives'))

        def native_ask():
            seed('ask'); audit = select()
            assert audit['action'] == 'ask' and audit['native_choice_claim'] is True
            assert audit['decision_layer'] == 'learned-deliberative'
            obs = runtime._hf2_resolution_observation['thought']
            assert [u.kind for u in obs.resolution_content] == ['qud-alternatives']
            assert obs.native_utterance.native_text == 'Did she leave?: sara / mira?'
            assert obs.native_utterance.grammar_frames == ['native-resolution-ask-qud-alternatives']
            return dict(audit=audit_summary(audit), surface=obs.native_utterance.native_text,
                        note='Ask carries no clarify-only primary; its QUD must remain visible.')
        check('09a_native_ask_geometry_preserves_sole_qud', native_ask)

        def ties():
            seed(tied=True); audit = select()
            assert audit['action'] is None and audit['native_choice_claim'] is False
            assert audit['selection_status'] == 'unresolved-exact-speech-act-consequence-geometry-tie'
            assert runtime._hf2_resolution_observation is None
            return audit_summary(audit)
        check('09b_tied_geometry_does_not_choose', ties)

        def missing_geometry():
            seed('clarify'); del runtime.state.cognition.speech_act_development.action_pre_knots['ask']
            audit = select(); assert audit['action'] is None and audit['native_choice_claim'] is False
            assert audit['selection_status'] == 'unresolved-insufficient-speech-act-consequence-geometry'
            return audit_summary(audit)
        check('09c_incomplete_geometry_does_not_choose', missing_geometry)

        def calibration():
            for action in ('clarify', 'ask'):
                plan = build_operator_resolution_calibration(action=action, authenticated_owner=True,
                    current_structure=current_structure, existing_question_candidates=['Existing native question?'])
                assert plan.executable and plan.origin == 'operator-directed-calibration-not-native-choice'
                assert plan.authority['operator_execution'] is True
                assert all(v is False for k, v in plan.authority.items() if k not in {'operator_execution', 'authentication'})
                denied = build_operator_resolution_calibration(action=action, authenticated_owner=False,
                    current_structure=current_structure, existing_question_candidates=['Existing native question?'])
                assert not denied.executable and denied.authority['native_choice'] is False
            return dict(origin=plan.origin, authority=dict(plan.authority), unauthenticated_rejected=True)
        check('10_owner_calibration_never_native_choice', calibration)

        def alternatives_order():
            primary, q = ref_rows
            reverse = replace(q, alternatives=tuple(reversed(q.alternatives)),
                source_units=(q.source_units[0], q.source_units[1], 'candidate:mira', 'candidate:sara'))
            u, units = render((primary, reverse))
            assert units[0].alternatives == ['sara', 'mira'] and units[1].alternatives == ['mira', 'sara']
            assert u.utterance_plan == ['she: sara / mira?', 'Did she leave?: mira / sara?']
            return dict(surface=u.native_text, order_preserved=True, ranking_added=False)
        check('11_all_alternatives_and_source_order_preserved', alternatives_order)

        def authority():
            u, units = render((*ref_rows, *event_rows, *reason_rows))
            assert len(units) == 8 and len(u.utterance_plan) == 8
            assert all(all(v is False for k, v in x.model_dump().items() if k.endswith('_authority')) for x in units)
            return dict(unit_count=len(units), all_content_authority_flags_false=True,
                inventory_unchanged_after_realization=True,
                selector_authority_note='The existing native selector owns speech_act_selection=True; content and eligibility do not. This fixture does not change that division.')
        check('12_zero_authority_typed_inventory_is_preserved', authority)

        def independent_event_sources():
            primary = [r for r in event_rows if r.kind == 'event-role-alternatives']
            same = replace(primary[0], source_id='event-role-independent', source_units=('event:1:0', *primary[0].source_units[1:]))
            u, units = render((primary[0], same))
            assert len(units) == len(u.utterance_plan) == 2
            assert u.utterance_plan[0] == u.utterance_plan[1]
            return dict(surface=u.native_text, ids=[x.source_id for x in units])
        check('13_independent_event_sources_identical_text', independent_event_sources)

        def mismatched_source():
            p, q = ref_rows
            q = replace(q, source_id='question-sentence-0:other-reference',
                source_units=(q.source_units[0], 'unresolved-source:other-reference', *q.source_units[2:]))
            u, _ = render((p, q)); assert len(u.utterance_plan) == 2
            return dict(surface=u.native_text, explicit_source_link_matches=False)
        check('14_different_source_ids_do_not_collapse', mismatched_source)

        def distinct_options():
            p, q = ref_rows
            q = replace(q, alternatives=('sara', 'omar'),
                source_units=(q.source_units[0], q.source_units[1], 'candidate:sara', 'candidate:omar'))
            u, _ = render((p, q)); assert len(u.utterance_plan) == 2 and 'omar' in u.native_text
            return dict(surface=u.native_text, alternative_sets_differ=True)
        check('15_distinct_alternative_sets_do_not_collapse', distinct_options)

        def independent_provenance():
            p, q = ref_rows
            surfaces = []
            for sources in ((q.source_units[0], *q.source_units[2:]),
                            (*q.source_units, 'unresolved-source:independent'),
                            (*q.source_units, 'independent-source:additional')):
                u, _ = render((p, replace(q, source_units=sources)))
                assert len(u.utterance_plan) == 2; surfaces.append(u.native_text)
            return dict(cases=['no-explicit-link', 'multiple-source-links', 'additional-independent-provenance'], surfaces=surfaces)
        check('16_independent_or_unlinked_qud_provenance_survives', independent_provenance)

        def wrong_event():
            _, units = render(ref_rows)
            units[0] = units[0].model_copy(update={'source_event_id': uuid4()})
            u, _ = render((), explicit_units=units)
            assert u.native_text == 'Did she leave?: sara / mira?'
            return dict(surface=u.native_text, ineligible_primary_cannot_cover_qud=True)
        check('17_wrong_event_primary_cannot_hide_valid_qud', wrong_event)

        def historical_contract():
            rows = native_current_turn_alternative_sources(analyze_dialogue_structure('Where is she?',
                recent_referents=[{'surface': 'Mira', 'kind': 'person'}, {'surface': 'Sara', 'kind': 'person'}]))
            u, _ = render(rows)
            assert u.native_text == 'she: Sara / Mira? Where is she?: Sara / Mira?'
            return dict(surface=u.native_text, stale_duplicate_contract_confirmed=True,
                        historical_test_changed=False)
        check('18_historical_duplicate_string_confirmed', historical_contract, 'defect-reproduction')

        after = fingerprint(root)
        assert before == after, 'Immutable source bytes changed'
        report = dict(
            schema='HF2-M4C3R-DISPOSABLE-POST0021-v1',
            generated_at=datetime.now(timezone.utc).isoformat(),
            repository='RugBlade/Yggdrasil', branch='stage8B/v0.8.2-conversation-completion-hf2',
            starting_head='14db100ae2c69798ce8654dbb548b46e21534512',
            harness_source_commit=os.getenv('GITHUB_SHA'), run_id=os.getenv('GITHUB_RUN_ID'),
            artifact_id=10585938051, artifact_bytes=len(data), artifact_sha256=ARTIFACT_SHA256,
            sealed_published_run_id=35448750669, sealed_published_job_id=105912125537,
            published_source_commit='aacabb590c963d8630f4c72802f12693f61f23b9',
            source_archive_sha256=SOURCE_SHA256, source_archive_bytes=len(source),
            source_file_count=len(before), published_python_hashes_verified=len(published_hashes.splitlines()),
            source_bytes_unchanged=before == after, source_files=before,
            environment=dict(python=sys.version, packages={p: importlib.metadata.version(p) for p in ('pydantic', 'Pillow', 'httpx')}),
            results=results, checks_passed=sum(r['status'] == 'PASS' for r in results),
            checks_failed=sum(r['status'] == 'FAIL' for r in results),
            controls_passed=all(r['status'] == 'PASS' for r in results if r['category'] == 'control'),
            defect_reproductions_passed=all(r['status'] == 'PASS' for r in results if r['category'] == 'defect-reproduction'),
            runtime_correction_required=all(r['status'] == 'PASS' for r in results),
            corrected_surface_verified=False, runtime_candidate_created=False,
            ordinary_0022_published=False, m4c3r_sealed=False, m4c3q_sealed=True,
            stage8b_complete=False, live_runtime_touched=False, canonical_db_touched=False,
            certification_claim=False, final_deployment_status='FINAL_LIVE_DEPLOYMENT_PACKAGE_NOT_YET_AUTHORIZED',
            limitations=[
                'Characterization of unchanged post0021; no correction or candidate has been tested.',
                'Consequence state is a labeled synthetic fixture using the existing learning/selector path, not evidence of live experience.',
                'Authority flags on typed content stay false; the native selector retains its pre-existing selection responsibility.',
                'Independent/malformed correspondence controls include explicitly labeled synthetic typed-input cases.',
                'M4C3Q sealed suites were not rerun.',
            ],
        )
        (args.output / 'verification.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        print(json.dumps({k: report[k] for k in ('checks_passed', 'checks_failed', 'controls_passed', 'defect_reproductions_passed', 'source_bytes_unchanged', 'runtime_correction_required')}))
        return 1 if report['checks_failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
