"""Read-only local characterization of the exact failed M4C3S candidate.

No source edit, candidate replacement, whole-suite rerun or native action selection.
"""
import sys,json,hashlib
from pathlib import Path
from noeron.inference import parse_surface_logic_detailed, infer, proposition_key
from noeron.math.models import LogicalProposition as P, LogicalQuery as Q
from noeron.math import dkt
from noeron.reasoning import build_multi_memory_reasoning

MODE=sys.argv[1]
checks=[]
def check(name,condition,evidence):
    checks.append({'id':name,'status':'PASS' if condition else 'FAIL','evidence':evidence})
def canon(rows):return [p.canonical() for p in rows]
def workspace(pp,q,**kw):
    return build_multi_memory_reasoning(dkt.reference_knot(),[],logical_propositions=pp,logical_query=q,**kw)

text='The box is red. Correction: the box is blue. What color is the box?'
pp,q,_=parse_surface_logic_detailed(text,{})
r=infer(pp,q);derived,steps,answers,status=r
primary={'input':[p.model_dump() for p in pp],'derived':canon(derived),'step_rules':[s.rule for s in steps],
         'answers':canon(answers),'status':status}
check('unchanged_bounded_answer_and_both_parsed_inputs',set(canon(pp))=={'box::is::red','box::is::blue'} and canon(answers)==['box::is::blue'] and status=='unique-proof-supported-answer',primary)
wq=Q(kind='why-proposition',subject='box',relation='is',object='blue')
wr=infer(pp,wq)
why={'answers':canon(wr[2]),'status':wr[3],'steps':[s.model_dump() for s in wr[1]]}

if MODE=='sealed':
    check('historical_step_slot_contains_one_admission_event',[s.rule for s in steps].count('bounded-correction-supersession')==1,primary)
    check('historical_direct_why_misclassifies_corrected_target_as_own_support',canon(wr[2])==['box::is::blue'],why)
else:
    from noeron.direct_proof import gate_compatible
    from noeron.reasoning import _logical_provenance_envelopes
    check('one_typed_zero_authority_admission_event_preserved',len(r.admission_audit)==1 and r.admission_audit[0]=={
      'kind':'bounded-correction-supersession','old_key':proposition_key(pp[0]),'new_key':proposition_key(pp[1]),
      'removed_input_indexes':[0],'control_input_index':1,'role':'admission-event-not-formal-proof',
      'semantic_truth_authority':False,'answer_authority':False},r.admission_audit)
    check('event_excluded_from_formal_ledger_and_steps',not steps and not r.ledger.records and r.admitted_indexes==[1] and r.ledger.proof_ledger_complete,
          {'steps':primary['step_rules'],'records':r.ledger.records,'indexes':r.admitted_indexes,'complete':r.ledger.proof_ledger_complete})
    check('corrected_target_does_not_explain_itself',not wr.candidates and wr.status=='no-proof-supported-answer',why)
    ws=workspace(pp,q)
    restored=type(ws).model_validate_json(ws.model_dump_json())
    check('actual_reasoning_and_serialization_keep_admission_event',len(ws.proof_admission_audit)==1 and json.dumps(restored.proof_admission_audit)==json.dumps(json.loads(ws.model_dump_json())['proof_admission_audit']) and canon(ws.answer_candidates)==['box::is::blue'] and not ws.inference_steps,
          {'audit':ws.proof_admission_audit,'roundtrip_audit':restored.proof_admission_audit,'answers':canon(ws.answer_candidates),'gate':ws.proof_gate_status})
    why_ws=workspace(pp,wq)
    check('response_and_autonomous_content_do_not_treat_admission_as_proof',not why_ws.answer_candidates and not why_ws.autonomous_proof_candidates and len(why_ws.proof_admission_audit)==1,
          {'answers':canon(why_ws.answer_candidates),'autonomous':canon(why_ws.autonomous_proof_candidates),'gate':why_ws.proof_gate_status})
    current=pp[1];extras=[P(subject='crate',relation='is',object='red'),P(subject='box',relation='has',object='red'),P(subject='box',relation='is',object='red',modality='possible'),P(subject='box',relation='is',object='red',universal=True)]
    scoped=infer([pp[0],*extras,current],q)
    check('correction_respects_subject_relation_modality_universal_bounds',set(scoped.admitted_indexes)=={1,2,3,4,5} and len(scoped.admission_audit)==1,
          {'admitted_indexes':scoped.admitted_indexes,'audit':scoped.admission_audit})
    repeated=infer([pp[0],pp[0].model_copy(deep=True),pp[1]],q)
    check('duplicate_removed_observations_have_one_event_with_both_indexes',len(repeated.admission_audit)==1 and repeated.admission_audit[0]['removed_input_indexes']==[0,1],repeated.admission_audit)
    natural='If Mira is ready, Mira is calm. If Mira is rested, Mira is calm. Mira is ready. Mira is rested. Why is Mira calm?'
    mp,mq,_=parse_surface_logic_detailed(natural,{})
    route=infer([*pp,*mp],mq)
    check('independent_formal_routes_coexist_with_separate_admission_audit',len(route.ledger.records)==2 and len(route.steps)==2 and len(route.admission_audit)==1 and len(route.candidates)==4,
          {'rules':[s.rule for s in route.steps],'audit':route.admission_audit,'answers':canon(route.candidates)})
    tiny=infer([*pp,*mp],mq,max_proof_records=1)
    tiny_ws=workspace([*pp,*mp],mq,max_proof_records=1)
    check('tiny_proof_budget_retains_audit_and_blocks_both_content_consumers',not tiny.ledger.proof_ledger_complete and len(tiny.admission_audit)==1 and not tiny.candidates and len(tiny_ws.proof_admission_audit)==1 and not tiny_ws.answer_candidates and not tiny_ws.autonomous_proof_candidates,
          {'complete':tiny.ledger.proof_ledger_complete,'audit':tiny.admission_audit,'response':canon(tiny_ws.answer_candidates),'autonomous':canon(tiny_ws.autonomous_proof_candidates),'status':tiny_ws.answer_selection_status})
    zero=infer(pp,q,max_steps=0,max_proof_records=0)
    check('admission_audit_does_not_spend_formal_budgets',zero.ledger.proof_ledger_complete and len(zero.admission_audit)==1 and canon(zero.candidates)==['box::is::blue'],
          {'closure_steps':zero.ledger.conclusion_steps_used,'proof_record_lower_bound':zero.ledger.proof_record_lower_bound,'audit':zero.admission_audit})
    envelopes=_logical_provenance_envelopes(pp,origin='current-turn',source_turn=1)
    good=gate_compatible(r,q,[(pp[i],envelopes[i]) for i in r.admitted_indexes])
    missing=gate_compatible(r,q,[])
    check('separate_audit_does_not_bypass_missing_provenance',len(good.eligible_candidates)==1 and not missing.eligible_candidates,
          {'with_provenance':good.status,'missing_provenance':missing.status,'missing_audits':missing.audits})

out={'mode':MODE,'source_module':__import__('noeron.inference',fromlist=['x']).__file__,'checks':checks,'passed':sum(c['status']=='PASS' for c in checks),'failed':sum(c['status']=='FAIL' for c in checks),
     'scope':'diagnostic characterization, not a replacement-candidate gate; no source changed'}
Path(__file__).with_name(MODE+'_diagnosis.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'mode':MODE,'passed':out['passed'],'failed':out['failed'],'checks':[{'id':c['id'],'status':c['status']} for c in checks]},indent=2))
if out['failed']:sys.exit(1)
