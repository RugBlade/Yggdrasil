"""New disposable runtime-compatibility gate on the exact sealed post0022 bytes.

Does not run either completed M4C3S harness or any sealed parent CI gate.
Experimental source copies are compiled and exercised, then discarded.
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
import shutil
import sys
import tarfile
import tempfile
import traceback
from types import SimpleNamespace
from uuid import UUID
import zipfile

ARTIFACT_SHA='b4f45fe3db4af1a019443cae1c563f9e3c371bad04708277fed8e0b1ed6207e0'
SOURCE_SHA='2d48868a39883be1a19399dc55f9735806b8cfa050d4136757be0d5fed3c05bd'
SHA=lambda b:hashlib.sha256(b).hexdigest()
EXPECTED_CHANGED={'inference.py','reasoning.py','math/models.py','cognition/models.py',
                  'cognition/kernel.py','conversation_proof.py','conversation_resolution.py'}

def hashes(root):
    return {str(p.relative_to(root)):SHA(p.read_bytes()) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--artifact',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    sys.dont_write_bytecode=True
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    blob=args.artifact.read_bytes(); assert SHA(blob)==ARTIFACT_SHA and len(blob)==679959
    with zipfile.ZipFile(io.BytesIO(blob)) as z:source=z.read('m4c3r-exact-post0022-published-source.tar.gz')
    assert SHA(source)==SOURCE_SHA and len(source)==663382
    checks=[]
    def check(name,fn,category='runtime_compatibility'):
        try:
            evidence=fn();checks.append(dict(id=name,category=category,status='PASS',evidence=evidence))
            print('PASS',name,flush=True)
        except Exception:
            checks.append(dict(id=name,category=category,status='FAIL',error=traceback.format_exc()))
            print('FAIL',name,checks[-1]['error'],flush=True)
    with tempfile.TemporaryDirectory(prefix='m4c3s-runtime-compatibility-') as td:
        td=Path(td);immutable=td/'immutable';overlay=td/'overlay'
        with tarfile.open(fileobj=io.BytesIO(source)) as t:t.extractall(immutable,filter='data')
        before=hashes(immutable);assert len(before)==58
        shutil.copytree(immutable,overlay)
        from install_disposable import install
        install(overlay,Path(__file__).parent)
        after=hashes(overlay)
        changed={p.removeprefix('src/noeron/') for p in before if before[p]!=after[p]}
        assert changed==EXPECTED_CHANGED,(changed,EXPECTED_CHANGED)
        assert set(after)-set(before)=={'src/noeron/direct_proof.py'}
        for p in overlay.rglob('*.py'):compile(p.read_bytes(),str(p),'exec')
        sys.path[:0]=[str(overlay),str(overlay/'src')]
        from noeron.direct_proof import infer_compatible,gate_compatible,typed_id,admit
        from noeron.inference import parse_surface_logic_detailed,proposition_key,infer,_legacy_infer_for_disposable_comparison
        from noeron.math.models import LogicalProposition as P,LogicalQuery as Q,KnotState,MultiMemoryReasoningMathState,MathKernelState
        from noeron.reasoning import build_multi_memory_reasoning,_logical_provenance_envelopes
        from noeron.conversation_proof import AmbiguityConstraint,normalize_inference_steps
        from noeron.conversation_premises import ConversationalPremiseEnvelope,NativeGeometryTrace
        from noeron.cognition import models as cm
        from noeron.cognition.kernel import GeometricCognitionKernel
        from noeron.math import dkt
        from noeron.math.affect import proto_affective_state
        from noeron.models import CognitiveEvent,EventKind,NoeronState
        from noeron.llm import MockLanguageEngine
        from noeron.memory import LocalEventStore
        from noeron.orchestrator import Noeron
        from noeron.conversation_resolution import native_current_turn_alternative_sources,resolution_content_units,build_operator_resolution_calibration
        from noeron.conversation_actions import observe_resolution_transition
        from noeron.language_dialogue import analyze_dialogue_structure,referent_mentions
        from noeron.development import NativeLanguageFaculty

        natural='If Mira is ready, Mira is calm. If Mira is rested, Mira is calm. Mira is ready. Mira is rested. Why is Mira calm?'
        premises,why,_=parse_surface_logic_detailed(natural)
        exact=why.model_copy(update={'kind':'exact-proposition'})
        target='mira::is::calm';targetkey=('mira','is','calm',True,False,'')
        key=lambda p:proposition_key(p)
        def bindings(pp,origin='current-turn'):
            return list(zip(pp,_logical_provenance_envelopes(pp,origin=origin,source_turn=1),strict=True))
        def work(pp= None,query=None,**kwargs):
            return build_multi_memory_reasoning(dkt.reference_knot(),[],logical_propositions=premises if pp is None else pp,
                logical_query=why if query is None else query,**kwargs)
        def evidence(r):
            return {'answers':[p.model_dump() for p in r.answer_candidates],
                'records':[s.model_dump() for s in r.inference_steps], 'confidence':r.confidence,
                'confidence_evidence':r.confidence_evidence,'complete':r.proof_ledger_complete,
                'gate':r.proof_gate_status,'ledger':r.proof_ledger}
        integrated=work()
        check('integrated_why_has_two_routes_and_four_supports',lambda:assert_why(integrated,premises,target))

        def route_confidences():
            pp=[p.model_copy(update={'confidence':.2 if 'ready' in (p.subject,p.object) or 'ready' in p.subject else .9}) for p in premises]
            outcomes=[]
            for order in permutations(pp):
                r=work(list(order),exact)
                vals=sorted(s.confidence for s in r.inference_steps if s.conclusion==target)
                assert vals==[.2,.9] and r.answer_candidates[0].confidence is None and r.confidence is None
                assert all(s.proof_record['confidence']['cross_route_reducer'] is None for s in r.inference_steps)
                outcomes.append(SHA(json.dumps(r.proof_ledger,sort_keys=True).encode()))
            assert len(set(outcomes))==1
            return {'permutations':len(outcomes),'route_confidences':[.2,.9],'aggregate':None,'ledger_sha256':outcomes[0]}
        check('real_reasoning_preserves_02_09_across_24_orders',route_confidences)

        families=[('atomic',[P(subject='a',relation='implies',object='t'),P(subject='b',relation='implies',object='t'),P(subject='a',relation='true',object='true'),P(subject='b',relation='true',object='true')],Q(kind='exact-proposition',subject='t',relation='true',object='true')),
            ('transitive',[P(subject='a',relation='implies',object='b'),P(subject='a',relation='implies',object='c'),P(subject='b',relation='implies',object='d'),P(subject='c',relation='implies',object='d')],Q(kind='exact-proposition',subject='a',relation='implies',object='d'))]
        for label,text in [('universal-positive','Every scholar is careful. Every teacher is careful. Mira is scholar. Mira is teacher.'),
                           ('universal-negative','No scholar is careful. No teacher is careful. Mira is scholar. Mira is teacher.')]:
            pp,_,_=parse_surface_logic_detailed(text);families.append((label,pp,Q(kind='exact-proposition',subject='mira',relation='is',object='careful')))
        for label,pp,q in families:
            def family(pp=pp,q=q):
                r=work(pp,q);assert len(r.answer_candidates)==1
                aa=r.answer_candidates[0];rr=[s for s in r.inference_steps if tuple(s.proof_record['conclusion_key'])==key(aa)]
                assert len(rr)==2 and aa.confidence is None and r.proof_ledger_complete
                return evidence(r)
            check('integrated_'+label+'_parallel_routes',family)

        def scalar_zero():
            pp=[premises[0].model_copy(update={'confidence':.7}),premises[2].model_copy(update={'confidence':0.0})]
            r=work(pp,exact)
            assert len(r.inference_steps)==1 and r.confidence==0.0 and r.answer_candidates[0].confidence==0.0
            normalized=normalize_inference_steps([{'rule':'r','premises':['p'],'conclusion':'q','confidence':0},
                {'rule':'r','premises':['p'],'conclusion':'q','confidence':None}])
            assert normalized[0].confidence==0.0 and normalized[1].confidence is None
            return evidence(r)
        check('single_route_zero_is_numeric_zero_not_default_or_absence',scalar_zero)

        def direct_target():
            pp=premises+[P(subject='mira',relation='is',object='calm',confidence=.8)]
            r=work(pp);assert len(r.inference_steps)==2 and len(r.answer_candidates)==4
            rr=infer(pp,exact);assert rr.candidates[0].confidence is None and rr.ledger.conclusion_steps_used==0
            bare=work([pp[-1]]);assert not bare.answer_candidates and not bare.inference_steps
            return {'with_routes':evidence(r),'bare_status':bare.answer_selection_status,'direct_target_aggregate':None}
        check('direct_target_preserves_derivations_bare_truth_is_not_explanation',direct_target)

        def nested_cycle():
            pp=[P(subject='a',relation='implies',object='b'),P(subject='b',relation='implies',object='c'),
                P(subject='c',relation='implies',object='a'),P(subject='a',relation='true',object='true')]
            q=Q(kind='exact-proposition',subject='c',relation='true',object='true');r=work(pp,q)
            assert r.proof_ledger_complete and r.answer_candidates and r.confidence is None
            ids=[s.proof_record['record_id'] for s in r.inference_steps]
            assert len(ids)==len(set(ids)) and len(ids)<30
            assert any(s.confidence is None for s in r.inference_steps)
            return evidence(r)
        check('cyclic_nested_symbolic_routes_pass_models_and_conservative_audit',nested_cycle)

        def duplicates():
            r=work(premises+premises);assert r.proof_ledger==integrated.proof_ledger
            return {'records':len(r.inference_steps),'sources':len(r.proof_ledger['sources'])}
        check('reasoning_duplicate_observations_do_not_multiply_proof_records',duplicates)

        def consumer(result):
            state=NoeronState();state.math_kernel.reasoning=result
            event=CognitiveEvent(id=UUID('00000000-0000-0000-0000-000000000073'),kind=EventKind.USER_MESSAGE,source='disposable-consumer',content='Why?')
            fixture=SimpleNamespace(state=state.math_kernel,retrieved=[],experience_knot=dkt.reference_knot(),consolidation=SimpleNamespace(score=0.0))
            k=GeometricCognitionKernel()
            return k.response(event,state,fixture),k.autonomous(state,[],event,fixture)
        def thoughts():
            r=work(query=exact);response,autonomous=consumer(r)
            for thought in (response,autonomous):
                assert thought.propositions and thought.propositions[0].confidence is None
                assert thought.propositions[0].proof_evidence['ledger_complete'] is True
                assert len(thought.propositions[0].proof_evidence['confidence']['producer_record_ids'])==2
                loaded=cm.NativeThought.model_validate_json(thought.model_dump_json())
                assert loaded.propositions[0].confidence is None
            assert not autonomous.should_surface
            return {'response':response.model_dump(mode='json'),'autonomous':autonomous.model_dump(mode='json')}
        check('response_autonomous_and_serialization_preserve_undefined_confidence',thoughts)

        for mode,kwargs in [('proof',{'prototype_max_proof_records':1}),('closure',{'prototype_max_conclusion_steps':0})]:
            def budget(kwargs=kwargs):
                r=work(query=exact,**kwargs);assert r.proof_ledger_complete is False and not r.answer_candidates
                assert r.proof_gate_status=='proof-gated-incomplete-ledger'
                assert not r.autonomous_proof_candidates
                response,autonomous=consumer(r)
                assert not response.propositions and not autonomous.propositions
                assert r.confidence is None and response.confidence is None
                return {'reasoning':evidence(r),'response_proof_evidence':response.proof_evidence,
                        'autonomous_proof_evidence':autonomous.proof_evidence}
            check(mode+'_budget_incompleteness_reaches_both_content_consumers',budget)
        def max_one():
            r=infer(premises,why,max_steps=1,max_proof_records=2)
            assert r.ledger.proof_ledger_complete and len(r.steps)==2 and r.ledger.conclusion_steps_used==1
            legacy_four=tuple(r);assert len(r)==4 and r[3]==legacy_four[3]
            return {'conclusion_steps':1,'proof_records':2,'legacy_unpack_arity':len(r)}
        check('public_infer_four_item_compatibility_and_separate_max_steps_budget',max_one)

        def typed_collision():
            p=P(subject='scholar',relation='is',object='careful');u=p.model_copy(update={'universal':True})
            q=Q(kind='exact-proposition',subject='scholar',relation='is',object='careful');rr=infer([p,u],q)
            b=bindings([p,u]);audit=gate_compatible(rr,q,b)
            assert len(audit.eligible_candidates)==2
            missing=gate_compatible(rr,q,b[:1]);assert len(missing.eligible_candidates)==1 and not missing.eligible_candidates[0].universal
            r=work([p,u],q);rows=native_current_turn_alternative_sources(analyze_dialogue_structure('Which?'),r)
            options=[x for x in rows if x.kind=='proposition-alternatives'];assert len(options)==1 and len(set(options[0].alternatives))==2
            assert {tuple(json.loads(x)['proposition_key']) for x in options[0].alternatives}=={key(p),key(u)}
            return {'gate':audit.audits,'missing_one_typed_provenance':missing.audits,'options':options[0].alternatives}
        check('typed_universal_collision_keeps_provenance_and_surface_options_distinct',typed_collision)

        def conservative(kind):
            rr=infer(premises,exact);b=bindings(premises);aa=[]
            if kind=='missing':b=b[:-1]
            if kind=='conflict':b[-1]=(b[-1][0],replace(b[-1][1],status='conflict',conflict_with=('other',)))
            if kind=='scoped':aa=[AmbiguityConstraint('affected-second-route','controlled',(premises[-1].canonical(),),('x','y'))]
            if kind=='unscoped':aa=[AmbiguityConstraint('unscoped','controlled',(),('x','y'))]
            audit=gate_compatible(rr,exact,b,aa);assert not audit.eligible_candidates
            assert not any(audit.authority.values())
            return {'status':audit.status,'audits':audit.audits}
        for kind in ('missing','conflict','scoped','unscoped'):
            check('all_routes_'+kind+'_remains_blocked',lambda kind=kind:conservative(kind),'conservative_consumer')
        def autonomous_block():
            structure={'ambiguities':[{'id':'blocked-second-route','kind':'test-controlled',
                'affected_canonicals':[premises[-1].canonical()],'alternatives':['x','y']}]}
            r=work(query=exact,current_language_structure=structure)
            assert not r.answer_candidates and not r.autonomous_proof_candidates
            response,autonomous=consumer(r);assert not response.propositions and not autonomous.propositions
            return {'response_gate':r.proof_gate_status,'autonomous_eligible':0}
        check('autonomous_path_uses_same_all_route_conservative_audit',autonomous_block,'conservative_consumer')

        def parallel_provenance():
            context=dkt.reference_knot();memory_id=UUID('00000000-0000-0000-0000-000000000083')
            m=cm.KnotMemory(id=memory_id,source_event_id=memory_id,knot=context,logical_coordinates=[0.0]*8)
            observed=premises[2].model_copy(update={'confidence':.2,'source_record_id':'current-observation'})
            learned=SimpleNamespace(subject_surface=observed.subject,relation=observed.relation,object_surface=observed.object,
                confidence=.9,source_memory_id=memory_id,source_memory_ids=[memory_id],source_confidences={str(memory_id):.9})
            envelope=bindings([observed])[0][1]
            envelope=replace(envelope,origin='bounded-dialogue-turn',source_turn=4,confidence=.4,
                native_trace=NativeGeometryTrace(dkt_support_knot=context.model_dump(mode='python')))
            r=build_multi_memory_reasoning(context,[(0.0,m)],logical_propositions=[premises[0],observed],logical_query=exact,
                learned_language_propositions=[learned],post_closure_knot=context,bounded_dialogue_premises=[envelope])
            assert r.answer_candidates and r.confidence is None
            target_observations=[s for s in r.proof_ledger['sources'].values() if tuple(s['key'])==key(observed)]
            assert len(target_observations)==3 and sorted(s['confidence_readings'][0] for s in target_observations)==[.2,.4,.9]
            origins={p['origin'] for a in r.proof_support_audits for p in a.get('provenance',[])}
            assert origins=={'bounded-dialogue-turn','current-turn','dkt-retrieved-persistent'}
            # A pending, un-retrieved learned source is never admitted by the adapter.
            pending=work([premises[0],observed],exact,learned_language_propositions=[learned])
            assert all(s['source']!='persistent-language-proposition' for s in pending.proof_ledger['sources'].values())
            return evidence(r)
        check('parallel_current_bounded_DKT_sources_and_native_admission_preserved',parallel_provenance)

        def corrections():
            old=P(subject='mira',relation='is',object='ready',confidence=.2)
            new=P(subject='mira',relation='is',object='rested',confidence=.9,modifiers=['correction'])
            cases=[[old,new],[new,old],[old,new,old.model_copy(update={'confidence':.8})],
                   [old,new,new.model_copy(update={'modifiers':[]})],
                   [old.model_copy(update={'universal':True}),new]]
            evidence=[]
            q=Q(kind='relation-from-subject',subject='mira',relation='is')
            for mode in ('direct','reasoning'):
                for pp in cases:
                    legacy_pp=(list({p.canonical():p for p in pp}.values()) if mode=='reasoning' else pp)
                    _,_,legacy_answers,_=_legacy_infer_for_disposable_comparison(legacy_pp,q)
                    r=infer(pp,q,admission_mode=mode)
                    assert {key(p) for p in legacy_answers}=={key(p) for p in r.candidates}
                    assert all(s.rule!='bounded-correction-supersession' for s in r.steps)
                    evidence.append({'mode':mode,'input':[p.model_dump() for p in pp],
                        'admitted_keys':[key(p) for p in r.propositions],'admission_audit':r.admission_audit})
            rr=work([old,new],q);assert len(rr.proof_admission_audit)==1
            assert not work([old,new],Q(kind='why-proposition',subject='mira',relation='is',object='rested')).answer_candidates
            return {'cases':evidence,'correction_event_is_not_an_explanation':True}
        check('existing_direct_and_reasoning_correction_admission_matches_ten_controls',corrections)

        def query_compatibility():
            # Direct, non-colliding observed inputs isolate public query-selection
            # compatibility from the intended change in proof-record collection.
            pp=[P(subject='mira',relation='is',object='ready'),P(subject='sara',relation='is',object='calm'),
                P(subject='mira',relation='at',object='home'),P(subject='mira',relation='time-at',object='dawn'),
                P(subject='mira',relation='manner-with',object='care'),
                P(subject='mira',relation='is',object='late',polarity=False)]
            outcomes=[]
            for kind in ('derive-all','relation-between','relation-from-subject','relation-to-object','exact-proposition',
                         'why-proposition','copular-value-from-subject','relation-subjects','where-from-subject',
                         'when-from-subject','how-from-subject','none','unresolved-surface-question','unresolved-reference'):
                q=Q(kind=kind,subject='mira',relation='',object='ready')
                old=_legacy_infer_for_disposable_comparison(pp,q);new=infer(pp,q)
                assert {key(p) for p in old[2]}=={key(p) for p in new[2]} and old[3]==new[3],kind
                outcomes.append({'kind':kind,'status':new.status,'candidate_count':len(new.candidates)})
            return outcomes
        check('fourteen_public_query_families_keep_observed_content_contract',query_compatibility)

        def genuine_alternatives():
            pp=[P(subject='mira',relation='is',object=x) for x in ('ready','rested')]
            r=work(pp,Q(kind='relation-from-subject',subject='mira',relation='is'))
            assert len(r.answer_candidates)==2 and r.answer_selection_status.startswith('multiple-')
            rows=native_current_turn_alternative_sources(analyze_dialogue_structure('Which?'),r)
            assert any(x.kind=='proposition-alternatives' and len(x.alternatives)==2 and x.act=='' for x in rows)
            return {'answers':[p.canonical() for p in r.answer_candidates],'forced_choice':False}
        check('genuine_proposition_alternatives_stay_act_neutral',genuine_alternatives)

        runtimes=[]
        def ingest():
            evidence=[]
            for i,text in enumerate((natural,'If Mira is rested, Mira is calm. If Mira is ready, Mira is calm. Mira is rested. Mira is ready. Why is Mira calm?')):
                n=Noeron(MockLanguageEngine(),LocalEventStore(td/f'ingest-{i}.sqlite3'),terra_enabled=False)
                event=CognitiveEvent(id=UUID(int=100+i),kind=EventKind.USER_MESSAGE,source='disposable-compatibility-owner',content=text,
                    trusted=True,metadata={'owner_authenticated':True})
                reply=n.ingest(event);r=n.state.math_kernel.reasoning
                assert r.proof_ledger_complete and len(r.inference_steps)==2 and len(r.answer_candidates)==4
                assert r.confidence is None and n.state.cognition.last_thought.confidence is None
                assert reply.speech_act_audit['action'] is None and not reply.speech_act_audit['native_choice_claim']
                # Affect consumes pre-inference geometry, not undefined proof confidence.
                assert isinstance(n.state.math_kernel.affect.uncertainty,float)
                snapshot=n.state.model_dump_json();roundtrip=NoeronState.model_validate_json(snapshot)
                assert roundtrip.math_kernel.reasoning.confidence is None
                evidence.append({'answers':sorted(p.canonical() for p in r.answer_candidates),'records':len(r.inference_steps),
                    'thought_confidence':None,'proof_confidence':None,'action':reply.speech_act_audit['action'],
                    'affect_signature':n.state.math_kernel.affect.pattern_signature,'snapshot_bytes':len(snapshot.encode())})
                runtimes.append((n,event,reply.language_interpretation['structure']))
            assert evidence[0]['answers']==evidence[1]['answers']
            return {'complete_real_ingest_cases':evidence,'canonical_db_touched':False}
        check('two_complete_Noeron_ingest_orders_and_state_roundtrip',ingest,'full_ingest')

        def native_choice(act=None,tied=False,missing=False):
            n,event,structure=runtimes[0];state=n.state.cognition.speech_act_development;context=n.state.math_kernel.dkt.core_knot
            state.action_pre_knots={};state.action_post_knots={};state.action_observations={};state.transition_observations=0
            if act or tied:
                for i,name in enumerate(('clarify','ask','defer','remain-silent'),1):
                    pre=context.model_copy(deep=True)
                    if not tied and name!=act:pre.c0[0]+=i*.2
                    pre.invariant_signature=dkt.invariant_signature(pre)
                    observation=observe_resolution_transition(state,name,pre,context.model_copy(deep=True),admissible=True,
                        mean_fn=lambda old,new,count:new.model_copy(deep=True) if old is None else dkt.chart_mean([old,new],[count,1]),
                        source='synthetic-disposable-compatibility-consequence-fixture')
                    assert observation['learned'] and not observation['speech_act_selection_authority']
            if missing:state.action_observations.pop('ask')
            thought=n.state.cognition.last_thought.model_copy(deep=True)
            audit=n._resolution_speech_act_selection(thought,SimpleNamespace(state=n.state.math_kernel),event=event,current_structure=structure)
            if act is None or tied or missing:
                assert audit['action'] is None and not audit['native_choice_claim']
            else:
                assert audit['action']==act and audit['native_choice_claim'] and audit['decision_layer']=='learned-deliberative'
            assert not audit['programmed_eligibility_is_choice']
            return {'action':audit['action'],'native_choice_claim':audit['native_choice_claim'],'status':audit['selection_status']}
        for name,kwargs in [('blank',{}),('tied',{'tied':True}),('missing',{'act':'clarify','missing':True}),
                            ('learned-clarify',{'act':'clarify'}),('learned-ask',{'act':'ask'}),('learned-silent',{'act':'remain-silent'})]:
            check('integrated_proof_inventory_native_'+name,lambda kwargs=kwargs:native_choice(**kwargs),'native_choice')

        def calibration():
            plan=build_operator_resolution_calibration(action='ask',authenticated_owner=True,existing_question_candidates=('Why is Mira calm?',))
            denied=build_operator_resolution_calibration(action='ask',authenticated_owner=False,existing_question_candidates=('Why is Mira calm?',))
            assert plan.executable and not denied.executable and not plan.authority['native_choice']
            return {'origin':plan.origin,'authority':plan.authority}
        check('owner_calibration_preserves_operator_boundary',calibration,'native_choice')

        def sealed_surface():
            structure=analyze_dialogue_structure('Did she leave?',recent_referents=referent_mentions(analyze_dialogue_structure('Mira met Sara.')))
            rows=native_current_turn_alternative_sources(structure,integrated)
            units=resolution_content_units(rows,action='clarify',source_event_id=UUID(int=100))
            thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',resolution_content=units,
                mathematical_provenance=cm.MathematicalProvenance(source_event_id=UUID(int=100)))
            before=thought.model_dump_json();u=NativeLanguageFaculty().realize(thought,cm.LanguageFacultyState())
            assert before==thought.model_dump_json()
            assert u.utterance_plan[0]=='she: sara / mira?' and 'Did she leave?:' not in u.native_text
            proof=[r for r in rows if r.kind=='proof-alternatives'];assert len(proof)==1 and len(proof[0].alternatives)==2
            assert {json.loads(x)['record_id'] for x in proof[0].alternatives}=={s.proof_record['record_id'] for s in integrated.inference_steps}
            assert all(not v for unit in units for k,v in unit.model_dump().items() if k.endswith('_authority'))
            return {'reference_clause':u.utterance_plan[0],'typed_units':len(units),'surface_clauses':len(u.utterance_plan),
                    'proof_record_ids_preserved':True,'authority_false':True}
        check('sealed_0022_surface_correspondence_with_typed_proof_metadata',sealed_surface,'surface_control')

        def source_and_boundaries():
            assert before==hashes(immutable)
            for name,module in sys.modules.items():
                if name.startswith('noeron') and getattr(module,'__file__',None):
                    assert Path(module.__file__).is_relative_to(overlay/'src')
            for p in ('math/kernel.py','math/affect.py','orchestrator.py','conversation_actions.py','development.py',
                      'conversation_runtime_gate.py','conversation_reasoning.py','conversation_premises.py'):
                assert before['src/noeron/'+p]==after['src/noeron/'+p]
            assert not any(integrated.proof_ledger['authority'].values()) and not any(integrated.proof_gate_authority.values())
            return {'changed_runtime_copies':sorted(changed),'added_runtime_copy':'direct_proof.py','immutable_files':58,'live_runtime_touched':False,
                'canonical_db_touched':False,'speech_act_and_renderer_source_unchanged':True,
                'affect_pre_inference_geometry_source_unchanged':True}
        check('source_provenance_authority_and_unchanged_causal_boundaries',source_and_boundaries,'provenance')
        (out/'immutable_hashes.json').write_text(json.dumps(before,indent=2)+'\n')
        (out/'overlay_hashes.json').write_text(json.dumps(after,indent=2)+'\n')
        with tarfile.open(out/'disposable-overlay-source.tar.gz','w:gz') as t:
            for p in sorted(overlay.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:t.add(p,arcname=str(p.relative_to(overlay)))
    report={'schema':'M4C3S-DISPOSABLE-RUNTIME-COMPATIBILITY-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
        'input_artifact_id':10594550960,'input_artifact_sha256':ARTIFACT_SHA,'input_source_sha256':SOURCE_SHA,
        'passed':sum(c['status']=='PASS' for c in checks),'failed':sum(c['status']=='FAIL' for c in checks),'checks':checks,
        'changed_disposable_runtime_files':sorted(EXPECTED_CHANGED),
        'added_disposable_runtime_files':['direct_proof.py'],
        'previous_31_and_41_check_gates_rerun':False,'candidate_created':False,'ordinary_0023_published':False,
        'm4c3r_sealed':True,'m4c3s_sealed':False,'stage8b_complete':False,'live_runtime_touched':False,'canonical_db_touched':False,
        'certification_claim':False,'full_hf2_candidate_suite_run':False,
        'scope_status':'INTEGRATION_PROTOTYPE_ONLY_REQUIRES_FINAL_CONTRACT_REVIEW'}
    (out/'compatibility_report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','failed','candidate_created')}),flush=True)
    return int(report['failed']>0)


def assert_why(r,premises,target):
    assert r.proof_ledger_complete and len(r.inference_steps)==2 and len(r.answer_candidates)==4
    assert {p.canonical() for p in r.answer_candidates}=={p.canonical() for p in premises}
    assert target not in {p.canonical() for p in r.answer_candidates} and r.confidence is None
    return {'routes':2,'support_candidates':4,'workspace_confidence':None,'gate':r.proof_gate_status}

if __name__=='__main__':raise SystemExit(main())
