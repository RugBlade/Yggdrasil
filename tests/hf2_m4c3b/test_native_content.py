"""M4C3B exact-runtime behaviors. All consequence fixtures are synthetic test data.

Real DKT transport/reference/distance/ties are executed. No production state is
seeded, no live service is used, and no local tests are required by this file.
"""
from copy import deepcopy
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from noeron.cognition import models as cm
from noeron.conversation_actions import choose_resolution_act
from noeron.conversation_resolution import native_resolution_sources
from noeron.consequence import equal_affordance_post_manifold
from noeron.development import NativeLanguageFaculty
from noeron.english_egress import realize_native_thought
from noeron.initiative import InitiativePolicy
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.math.linalg import numerically_tied
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind, NoeronState
from noeron.orchestrator import Noeron

ACTS=('clarify','ask','defer','remain-silent')


@pytest.fixture
def runtime():
    n=Noeron.__new__(Noeron)
    n.state=NoeronState()
    n.state.math_kernel.dkt.core_knot=dkt.reference_knot()
    n.language=NativeLanguageFaculty()
    n._lock=RLock()
    n.store=SimpleNamespace(append_thought=Mock(),append_state=Mock())
    n._mark_speech_act_pending=Mock(side_effect=AssertionError('formation is not execution'))
    n._conversation_transport=Mock(side_effect=AssertionError('no transport in M4C3B'))
    n.renderer=Mock()
    return n


def current_turn(n,questions=(),text='She moved it.'):
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-m4c3b-test',content=text)
    n.state.last_event_id=event.id
    n.state.conversational_turn+=1
    thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',
        question_candidates=list(questions),
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id),
        causal_trace=['isolated-test-fixture'])
    structure=analyze_dialogue_structure(text,recent_referents=[
        {'surface':'Mira','kind':'person'}, {'surface':'Sara','kind':'person'},
        {'surface':'book','kind':'object'}, {'surface':'box','kind':'object'},
    ])
    reasoning=n.state.math_kernel.reasoning
    reasoning.proof_gate_unscoped_ambiguity_count=len(structure['ambiguities'])
    reasoning.proof_gate_status='proof-gated-unresolved-ambiguity'
    return event,thought,structure,SimpleNamespace(state=n.state.math_kernel)


def geometry_fixture(n,selected='clarify',tie=False):
    # All posts share one actual DKT knot. Unequal pre->post displacements produce
    # a unique transported minimum. This fixture is never default runtime state.
    st=n.state.cognition.speech_act_development
    context=n.state.math_kernel.dkt.core_knot
    for index,act in enumerate(ACTS,1):
        pre=context.model_copy(deep=True)
        if not tie and act!=selected: pre.c0[0]+=index*0.2
        pre.invariant_signature=dkt.invariant_signature(pre)
        st.action_pre_knots[act]=pre
        st.action_post_knots[act]=context.model_copy(deep=True)
        st.action_observations[act]=1
    st.transition_observations=4


def select(n,turn):
    event,thought,structure,result=turn
    return n._resolution_speech_act_selection(thought,result,event=event,current_structure=structure)


def test_real_geometry_forms_all_native_alternatives_without_execution(runtime):
    turn=current_turn(runtime)
    geometry_fixture(runtime)
    before=runtime.state.cognition.model_dump()
    original=turn[1].model_dump()
    out=select(runtime,turn)
    assert out['action']=='clarify' and out['native_choice_claim'] is True
    assert set(out['eligible_actions'])=={'clarify','remain-silent'}
    assert out['candidate_distances']['clarify']==0
    assert out['candidate_distances']['remain-silent']>0
    obs=runtime._hf2_resolution_observation
    thought=obs['thought']
    assert [u.alternatives for u in thought.resolution_content]==[['Sara','Mira'],['box','book']]
    assert all(u.unresolved for u in thought.resolution_content)
    assert thought.propositions==[] and thought.statement=='' and thought.question_candidates==[]
    assert thought.mathematical_provenance.source_event_id==turn[0].id
    assert thought.native_utterance.native_text=='she: Sara / Mira? it: box / book?'
    assert obs['english_text']=='She: Sara / Mira? it: box / book?'
    assert turn[1].model_dump()==original
    assert out['changes_response_content'] is False and out['changes_outward_transport'] is False
    assert out['content_formation']['executed'] is False
    for key in ('action_pre_knots','action_post_knots','action_observations','transition_observations','pending_action','operator_calibration_observations'):
        assert runtime.state.cognition.speech_act_development.model_dump()[key]==before['speech_act_development'][key]
    for key in ('language','last_thought','owner_relation','initiative_development','realization_development'):
        assert runtime.state.cognition.model_dump()[key]==before[key]
    runtime.store.append_thought.assert_not_called()
    runtime.store.append_state.assert_not_called()
    runtime._mark_speech_act_pending.assert_not_called()
    runtime._conversation_transport.assert_not_called()
    assert runtime.renderer.mock_calls==[]


@pytest.mark.parametrize('case',['fresh','missing','tie','incompatible-reference'])
def test_unresolved_geometry_forms_no_content(runtime,case):
    turn=current_turn(runtime)
    if case!='fresh': geometry_fixture(runtime,tie=case=='tie')
    st=runtime.state.cognition.speech_act_development
    if case=='missing': st.action_observations.pop('remain-silent')
    if case=='incompatible-reference': st.action_post_knots['remain-silent'].sobolev_order+=1
    out=select(runtime,turn)
    assert out['action'] is None and out['native_choice_claim'] is False
    assert out['content_formation']['content_count']==0
    assert runtime._hf2_resolution_observation is None
    if case=='fresh': assert st.action_observations=={} and st.transition_observations==0


@pytest.mark.parametrize('case',['diagnostic','singleton','string','mapping','mixed','duplicate','resolved','wrong-status','wrong-index','wrong-focus','unmatched-reference'])
def test_malformed_or_diagnostic_alternatives_cannot_be_native_content(case):
    structure=analyze_dialogue_structure('She moved.',recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    raw=structure['ambiguities'][0]
    if case=='diagnostic': raw.update(kind='event-role',alternatives='instrument-or-comitative-or-attachment')
    elif case=='singleton': raw['candidates']=['Mira']
    elif case=='string': raw['candidates']='Mira or Sara'
    elif case=='mapping': raw['candidates']={'Mira':1,'Sara':2}
    elif case=='mixed': raw['candidates']=['Mira',{'invented':'Sara'}]
    elif case=='duplicate': raw['candidates']=['Mira',' Mira ']
    elif case=='resolved': raw['resolved']=True
    elif case=='wrong-status': raw['status']='resolved-unique-candidate'
    elif case=='wrong-index': raw['token_index']=True
    elif case=='wrong-focus': raw['surface']='he'
    elif case=='unmatched-reference': structure['reference_candidates']=[]
    assert native_resolution_sources(structure)[0]==()


def test_no_dict_stringification_or_diagnostic_override_of_valid_references():
    structure=analyze_dialogue_structure('She moved.',recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    structure['ambiguities'][0]['alternatives']='invented parser label'
    refs,questions=native_resolution_sources(structure,[{'invented':'question'},'',None,'Existing native question?'])
    assert refs[0].alternatives==('Sara','Mira')
    assert [q.existing_question for q in questions]==['Existing native question?']


@pytest.mark.parametrize('case',['wrong-event','wrong-proof','wrong-digest','endogenous','nonconversational','empty','autonomous'])
def test_unbound_current_turn_cannot_select_or_form_content(runtime,case):
    turn=current_turn(runtime)
    geometry_fixture(runtime)
    event,thought,structure,_=turn
    if case=='wrong-event': runtime.state.last_event_id=uuid4()
    elif case=='wrong-proof': thought.mathematical_provenance.source_event_id=uuid4()
    elif case=='wrong-digest': structure['text_sha256']='old'
    elif case in ('endogenous','nonconversational'): event.metadata['nonconversational_observation' if case=='nonconversational' else case]=True
    elif case=='empty': event.content=''
    elif case=='autonomous': thought.kind=cm.NativeThoughtKind.OPEN_QUESTION
    out=select(runtime,turn)
    assert out['native_choice_claim'] is False
    assert out['content_formation']['current_turn_bound'] is False
    assert runtime._hf2_resolution_observation is None


def test_ask_copies_only_current_native_questions(runtime):
    turn=current_turn(runtime,questions=('Where is the lamp?',))
    runtime.state.cognition.last_thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',question_candidates=['Stale?'])
    runtime._hf2_resolution_turn={'questions':['Forged preview?']}
    geometry_fixture(runtime,selected='ask')
    out=select(runtime,turn)
    assert out['action']=='ask'
    obs=runtime._hf2_resolution_observation
    assert obs['thought'].native_utterance.native_text=='Where is the lamp?'
    assert obs['thought'].resolution_content[0].existing_question=='Where is the lamp?'


@pytest.mark.parametrize('action',['defer','remain-silent'])
def test_nonsemantic_selection_does_not_author_text_or_execute(runtime,action):
    turn=current_turn(runtime)
    turn[3].state.reasoning.logical_query.kind='property-of'
    geometry_fixture(runtime,selected=action)
    out=select(runtime,turn)
    assert out['action']==action
    assert out['content_formation']['status']=='selected-nonsemantic-act-no-content-or-execution'
    assert out['content_formation']['executed'] is False
    assert runtime._hf2_resolution_observation is None


def test_existing_proposition_answer_never_becomes_resolution(runtime):
    turn=current_turn(runtime)
    turn[1].propositions=[cm.NativeProposition(subject='lamp',relation='is',object='on',grounds=['proof'])]
    before=turn[1].model_dump()
    geometry_fixture(runtime)
    out=select(runtime,turn)
    assert out['requires_resolution'] is False
    assert out['content_formation']['ordinary_answer_preserved'] is True
    assert turn[1].model_dump()==before
    assert runtime._hf2_resolution_observation is None


@pytest.mark.parametrize('visibility,translation',[(False,False),(False,True),(True,False),(True,True)])
def test_private_observation_controls_do_not_select_or_train(runtime,visibility,translation):
    turn=current_turn(runtime)
    geometry_fixture(runtime)
    select(runtime,turn)
    controls=runtime.state.cognition.language.owner_communication_controls
    controls.internal_utterance_visibility=visibility
    controls.internal_utterance_translation=translation
    before=runtime.state.model_dump()
    out=runtime.owner_internal_utterance_observation()
    assert runtime.state.model_dump()==before
    if not visibility:
        assert out.get('resolution_observation') is None
    else:
        observation=out['resolution_observation']
        assert observation['native_utterance']['native_text']=='she: Sara / Mira? it: box / book?'
        assert bool(observation['english_translation'])==translation
        assert observation['executed'] is False
        observation['content'][0]['alternatives'].append('not native')
        assert 'not native' not in runtime._hf2_resolution_observation['thought'].resolution_content[0].alternatives


def test_resolution_text_not_serialized_into_public_audits_or_replayed(runtime):
    turn=current_turn(runtime)
    geometry_fixture(runtime)
    out=select(runtime,turn)
    assert 'native_utterance' not in out['content_formation']
    assert 'content' not in out['content_formation']
    saved=runtime.state.model_dump_json()
    assert 'she: Sara / Mira?' not in saved
    assert '_hf2_resolution_observation' not in saved
    runtime.state.last_event_id=uuid4()
    runtime.state.cognition.language.owner_communication_controls.internal_utterance_visibility=True
    assert runtime.owner_internal_utterance_observation()['resolution_observation'] is None


def test_native_model_and_egress_never_assert_alternatives(runtime):
    turn=current_turn(runtime)
    geometry_fixture(runtime)
    select(runtime,turn)
    native=runtime._hf2_resolution_observation['thought']
    encoded=native.model_dump_json()
    restored=cm.NativeThought.model_validate_json(encoded)
    assert restored.propositions==[] and restored.resolution_content==native.resolution_content
    english,audit=realize_native_thought(restored,restored.native_utterance)
    assert english=='She: Sara / Mira? it: box / book?'
    assert all(v is False for k,v in audit.items() if k.endswith('_authority'))
    restored.mathematical_provenance.source_event_id=uuid4()
    assert runtime.language.realize(restored,runtime.state.cognition.language).native_text==''


@pytest.mark.parametrize('invalid',[float('nan'),float('inf'),-1.0])
def test_invalid_distance_cannot_authorize_content(invalid):
    knot=dkt.reference_knot()
    out=choose_resolution_act(eligible_actions=('clarify','remain-silent'),context_geometry=knot,
        action_pre_geometry={a:knot for a in ACTS},action_post_geometry={a:knot for a in ACTS},
        action_observations={a:1 for a in ACTS},transport_fn=InitiativePolicy._transport_transition,
        reference_fn=equal_affordance_post_manifold,distance_fn=lambda a,b:invalid,tied_fn=numerically_tied)
    assert out['native_choice_claim'] is False and out['action'] is None
    assert out['selection_status']=='unresolved-invalid-native-consequence-distance'


@pytest.fixture
def isolated(tmp_path):
    return Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/'isolated.sqlite3'),terra_enabled=False)


def test_full_native_path_forms_current_reference_content_after_geometry(isolated,monkeypatch):
    n=isolated
    n.state.cognition.language.dialogue.recent_referents=[
        cm.DialogueReferent(surface='Mira',kind='person'),cm.DialogueReferent(surface='Sara',kind='person')]
    actual=n._resolution_speech_act_selection
    def capture(thought,result,**kwargs):
        # Only the learned-state fixture is synthesized. The current context is
        # the real result of IRG/DKT/regional EGR/RL-Frenet/DKT/cognition for input.
        assert result.state is n.state.math_kernel
        assert thought.mathematical_provenance.source_event_id==kwargs['event'].id
        geometry_fixture(n)
        return actual(thought,result,**kwargs)
    monkeypatch.setattr(n,'_resolution_speech_act_selection',capture)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-test',content='She moved.')
    reply=n.ingest(event)
    assert reply.security.allowed
    assert reply.speech_act_audit['action']=='clarify'
    obs=n._hf2_resolution_observation
    assert obs['thought'].native_utterance.native_text=='she: Sara / Mira?'
    assert obs['thought'].causal_trace[-1]=='native-unique-speech-act-predicted-post-state-hs-minimum'
    assert reply.text==reply.native_text==reply.english_text==''
    assert n.state.cognition.speech_act_development.pending_action==''
    assert n.state.cognition.speech_act_development.transition_observations==4
    assert n.owner_internal_utterance_observation().get('resolution_observation') is None
    n.ingest(CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-test',content='Rejected'),proposed_invariant_changes={'identity':'bad'})
    assert n._hf2_resolution_observation is None


def test_http_private_resolution_observation_requires_owner(isolated,monkeypatch):
    import noeron.api as api
    from fastapi.testclient import TestClient
    from noeron.auth import OwnerAuthenticator
    turn=current_turn(isolated)
    geometry_fixture(isolated)
    select(isolated,turn)
    isolated.state.cognition.language.owner_communication_controls.internal_utterance_visibility=True
    monkeypatch.setattr(api,'noeron',isolated)
    monkeypatch.setattr(api,'owner_auth',OwnerAuthenticator('test-only-m4c3b-token'))
    client=TestClient(api.app)
    unauth=client.get('/owner/internal-utterance/latest')
    assert unauth.status_code in (401,403)
    response=client.get('/owner/internal-utterance/latest',headers={'X-Noeron-Owner-Token':'test-only-m4c3b-token'})
    assert response.status_code==200
    assert response.json()['resolution_observation']['content']
