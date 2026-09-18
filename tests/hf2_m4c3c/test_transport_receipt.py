"""M4C3C: actual adapter send/receipt boundary on isolated test-only runtimes.

Consequence-state fixtures below are SYNTHETIC. Selection uses real native DKT
transport/reference/distance/ties; production defaults remain observation-free.
"""
import asyncio
import base64
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from noeron.cognition import models as cm
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind,NoeronReply,NoeronState,SecurityDecision,Stratum
from noeron.orchestrator import Noeron

CHANNEL='authenticated-owner-room-http'
ACTS=('clarify','ask','defer','remain-silent')


@pytest.fixture
def runtime(tmp_path):
    return Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/'isolated.sqlite3'),terra_enabled=False)


def seed_test_geometry(n,*,act='clarify',expression='express',tie=False):
    context=n.state.math_kernel.dkt.core_knot
    st=n.state.cognition.speech_act_development
    for i,a in enumerate(ACTS,1):
        pre=context.model_copy(deep=True)
        if a!=act:pre.c0[0]+=i*.2
        pre.invariant_signature=dkt.invariant_signature(pre)
        st.action_pre_knots[a]=pre;st.action_post_knots[a]=context.model_copy(deep=True)
        st.action_observations[a]=1
    st.transition_observations=4
    initiative=n.state.cognition.initiative_development
    for a in ('express','continue-private'):
        pre=context.model_copy(deep=True)
        if a!=expression and not tie:pre.c0[1]+=.5
        pre.invariant_signature=dkt.invariant_signature(pre)
        initiative.action_pre_knots[a]=pre;initiative.action_post_knots[a]=context.model_copy(deep=True)
        initiative.action_observations[a]=1
    initiative.admissible_post_knot=context.model_copy(deep=True)
    initiative.admissible_post_observations=2;initiative.transition_observations=2


def turn(n,*,act='clarify',expression='express',tie=False):
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-owner-test',content='She moved.',
        metadata={'owner_authenticated':True})
    n.state.last_event_id=event.id;n.state.conversational_turn+=1
    structure=analyze_dialogue_structure(event.content,recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    native=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',
        question_candidates=['Where is the lamp?'] if act=='ask' else [],
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
    n.state.math_kernel.reasoning.proof_gate_unscoped_ambiguity_count=1
    if act=='defer':n.state.math_kernel.reasoning.logical_query.kind='property-of'
    seed_test_geometry(n,act=act,expression=expression,tie=tie)
    out=n._resolution_speech_act_selection(native,SimpleNamespace(state=n.state.math_kernel),event=event,current_structure=structure)
    assert out['action']==act
    return event,native


def prepare(n,**kwargs):
    event,native=turn(n,**kwargs)
    prepared=n._prepare_resolution_transport(event,channel=CHANNEL)
    assert prepared is not None
    token,output=prepared
    return event,native,token,output


def transmit(n,token,text,*,failure=None,path='/room/message',status=200):
    from noeron.api import _ResolutionRoomResponse
    response=_ResolutionRoomResponse({'text':text},n,token)
    response.status_code=status
    messages=[]
    async def receive():return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        # The receipt and both pending exposures must still be absent during send.
        st=n.state.cognition.speech_act_development
        assert st.pending_execution_receipt is None and st.pending_action==''
        assert n.state.cognition.initiative_development.pending_expression_pre_knot is None
        if failure==message['type']:raise OSError('isolated failed channel send')
        messages.append(message)
    scope={'type':'http','method':'POST','path':path,'asgi':{'version':'3.0','spec_version':'2.4'}}
    asyncio.run(response(scope,receive,send))
    return messages


@pytest.mark.parametrize('act',['clarify','ask'])
def test_send_completion_is_the_first_execution_receipt_and_never_training(runtime,act):
    event,original,token,output=prepare(runtime,act=act)
    text,renderer,native,english,selection,_,_=output
    assert selection['action']=='express' and selection['native_choice_claim'] is True
    assert renderer is False and text==english
    before=runtime.state.cognition.model_dump()
    assert runtime.state.cognition.speech_act_development.pending_action==''
    assert runtime.state.cognition.initiative_development.pending_expression_pre_knot is None
    assert runtime.owner_internal_utterance_observation().get('resolution_observation') is None
    messages=transmit(runtime,token,text)
    assert [m['type'] for m in messages]==['http.response.start','http.response.body']
    assert json.loads(messages[-1]['body'])['text']==text
    st=runtime.state.cognition.speech_act_development
    receipt=st.pending_execution_receipt
    assert receipt.action==st.pending_action==act and receipt.event_id==event.id
    assert receipt.transport_text_sha256==hashlib.sha256(text.encode()).hexdigest()
    assert receipt.native_text_sha256==hashlib.sha256(native.encode()).hexdigest()
    assert receipt.peer_delivery_confirmed is False
    assert st.action_observations==before['speech_act_development']['action_observations']
    assert st.transition_observations==4 and st.operator_calibration_observations==0
    initiative=runtime.state.cognition.initiative_development
    assert initiative.transition_observations==2
    assert initiative.pending_expression_receipt_id==receipt.receipt_id
    assert runtime.store.latest_state().cognition.speech_act_development.pending_execution_receipt==receipt
    assert runtime.security.restore().cognition.speech_act_development.pending_execution_receipt==receipt
    assert runtime.state.cognition.owner_relation.model_dump()==before['owner_relation']
    assert runtime.state.cognition.realization_development.model_dump()==before['realization_development']
    assert original.propositions==[]


@pytest.mark.parametrize('failure',['http.response.start','http.response.body'])
def test_failed_send_never_marks_receipt_or_pending(runtime,failure):
    _,_,token,out=prepare(runtime)
    before=runtime.state.model_dump()
    with pytest.raises(OSError,match='failed channel'):
        transmit(runtime,token,out[0],failure=failure)
    assert runtime.state.model_dump()==before
    assert runtime._hf2_resolution_dispatch is None


@pytest.mark.parametrize('case',['body-change','empty','wrong-path','error-response','abandoned'])
def test_unverified_adapter_output_cannot_mark_pending(runtime,case):
    _,_,token,out=prepare(runtime)
    before=runtime.state.model_dump()
    if case=='abandoned':runtime.abandon_resolution_dispatch(token)
    transmit(runtime,token,'changed' if case=='body-change' else '' if case=='empty' else out[0],
        path='/message' if case=='wrong-path' else '/room/message',status=500 if case=='error-response' else 200)
    assert runtime.state.model_dump()==before
    assert runtime._hf2_resolution_dispatch is None


@pytest.mark.parametrize('case',['new-event','new-turn','new-geometry','new-residual','lost-act-choice','lost-express-choice','wrong-channel','wrong-hash'])
def test_stale_or_mismatched_completion_is_not_learnable(runtime,case):
    _,_,token,out=prepare(runtime)
    if case=='new-event':runtime.state.last_event_id=uuid4()
    elif case=='new-turn':runtime.state.conversational_turn+=1
    elif case=='new-geometry':runtime.state.math_kernel.dkt.core_knot.c0[0]+=.1
    elif case=='new-residual':runtime.state.math_kernel.egr.bridge_residual+=10
    elif case=='lost-act-choice':runtime.state.cognition.speech_act_development.last_native_choice_claim=False
    elif case=='lost-express-choice':runtime.state.cognition.initiative_development.last_native_choice_claim=False
    before=runtime.state.model_dump()
    result=runtime.complete_resolution_dispatch(token,channel='other' if case=='wrong-channel' else CHANNEL,
        text_sha256='bad' if case=='wrong-hash' else hashlib.sha256(out[0].encode()).hexdigest())
    assert result['receipt_recorded'] is False
    assert runtime.state.model_dump()==before
    assert runtime._hf2_resolution_dispatch is None


def test_capability_is_unforgeable_by_json_and_completion_is_one_shot(runtime):
    _,_,token,out=prepare(runtime)
    digest=hashlib.sha256(out[0].encode()).hexdigest()
    assert runtime.complete_resolution_dispatch(object(),channel=CHANNEL,text_sha256=digest)['receipt_recorded'] is False
    transmit(runtime,token,out[0])
    before=runtime.state.model_dump()
    assert runtime.complete_resolution_dispatch(token,channel=CHANNEL,text_sha256=digest)['receipt_recorded'] is False
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize('case',['no-owner','owner-command','override','endogenous','nonconversational','wrong-channel','stale','existing-pending'])
def test_channel_and_owner_controls_cannot_grant_resolution_execution(runtime,case):
    event,_=turn(runtime)
    if case=='no-owner':event.metadata['owner_authenticated']=False
    elif case=='owner-command':event.metadata['owner_command']=True
    elif case=='override':event.metadata['operator_realization_override']='native-direct'
    elif case in ('endogenous','nonconversational'):event.metadata['nonconversational_observation' if case=='nonconversational' else case]=True
    elif case=='stale':runtime.state.last_event_id=uuid4()
    elif case=='existing-pending':runtime.state.cognition.speech_act_development.pending_action='ask'
    before=runtime.state.model_dump()
    assert runtime._prepare_resolution_transport(event,channel='other' if case=='wrong-channel' else CHANNEL) is None
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize('case',['continue-private','tie','missing'])
def test_act_choice_never_implies_expression_even_with_owner_override_enabled(runtime,case):
    event,_=turn(runtime,expression='continue-private' if case=='continue-private' else 'express',tie=case=='tie')
    runtime.state.cognition.language.owner_communication_controls.response_channel_override=True
    if case=='missing':runtime.state.cognition.initiative_development.action_observations={}
    assert runtime._prepare_resolution_transport(event,channel=CHANNEL) is None
    assert runtime.state.cognition.speech_act_development.pending_action==''
    assert runtime.state.cognition.initiative_development.pending_expression_pre_knot is None


@pytest.mark.parametrize('act',['defer','remain-silent'])
def test_nonsemantic_acts_are_not_fabricated_text_executions(runtime,act):
    event,_=turn(runtime,act=act)
    assert runtime._hf2_resolution_observation is None
    assert runtime._prepare_resolution_transport(event,channel=CHANNEL) is None
    assert runtime.state.cognition.speech_act_development.last_execution_receipt is None


def test_direct_pending_marker_cannot_accept_an_asserted_receipt(runtime):
    event,_=turn(runtime)
    before=runtime.state.model_dump()
    out=runtime._mark_speech_act_pending('clarify',event.id,origin='native-resolution-asgi-send-completed',
        execution_receipt={'status':'asgi-response-body-sent'})
    assert out['pending'] is False and 'receipt-required' in out['status']
    assert runtime.state.model_dump()==before


def test_receipt_and_prepared_dispatch_do_not_train_on_restart_or_serialize_capability(runtime,tmp_path):
    event,_,token,out=prepare(runtime)
    reply=NoeronReply(text=out[0],state=runtime.state,security=SecurityDecision(allowed=True,reason='test',target_stratum=Stratum.ORDINARY))
    reply._resolution_dispatch=token
    assert '_resolution_dispatch' not in reply.model_dump_json()
    assert '_hf2_resolution_dispatch' not in runtime.state.model_dump_json()
    restored=Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/'fresh.sqlite3'),terra_enabled=False)
    restored.state=NoeronState.model_validate_json(runtime.state.model_dump_json())
    assert restored.complete_resolution_dispatch(token,channel=CHANNEL,text_sha256=hashlib.sha256(out[0].encode()).hexdigest())['receipt_recorded'] is False
    transmit(runtime,token,out[0])
    saved=NoeronState.model_validate_json(runtime.state.model_dump_json())
    assert saved.cognition.speech_act_development.transition_observations==4
    assert saved.cognition.speech_act_development.pending_execution_receipt.event_id==event.id


def later_result(n):
    state=n.state.math_kernel.model_copy(deep=True)
    state.dkt.security_admissible=True
    state.egr.bridge_residual=state.egr.balance_residual=state.rl.geodesic_acceleration_norm=0
    return SimpleNamespace(state=state)


@pytest.mark.parametrize('case',['same-event','pre-send-created','endogenous','nonconversational','missing-receipt','tampered-pre-knot'])
def test_only_a_later_conversational_receipted_outcome_can_train(runtime,case):
    original,_,token,out=prepare(runtime)
    transmit(runtime,token,out[0])
    st=runtime.state.cognition.speech_act_development
    receipt=st.pending_execution_receipt
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='later-test',content='Mira.',
        created_at=receipt.completed_at+timedelta(seconds=1))
    if case=='same-event':event.id=original.id
    elif case=='pre-send-created':event.created_at=receipt.completed_at-timedelta(seconds=1)
    elif case=='endogenous':event.metadata['endogenous']=True
    elif case=='nonconversational':event.metadata['nonconversational_observation']=True
    elif case=='missing-receipt':st.pending_execution_receipt=None
    elif case=='tampered-pre-knot':st.pending_pre_knot.c0[0]+=.1
    before=runtime.state.model_dump()
    assert runtime._resolve_pending_expression_outcome(later_result(runtime),event)['learned'] is False
    assert runtime._resolve_pending_speech_act_outcome(later_result(runtime),event)['learned'] is False
    runtime._mark_expression_pending(uuid4())  # cannot overwrite protected receipt
    assert runtime.state.model_dump()==before


@pytest.mark.parametrize('admissible',[True,False])
def test_later_native_outcome_learns_at_most_once_and_keeps_authorities_zero(runtime,admissible):
    _,_,token,out=prepare(runtime)
    transmit(runtime,token,out[0])
    st=runtime.state.cognition.speech_act_development
    receipt=st.pending_execution_receipt
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='later-test',content='Mira.',created_at=receipt.completed_at+timedelta(seconds=1))
    result=later_result(runtime)
    result.state.dkt.security_admissible=admissible
    expression=runtime._resolve_pending_expression_outcome(result,event)
    resolution=runtime._resolve_pending_speech_act_outcome(result,event)
    assert expression['learned'] is resolution['learned'] is admissible
    assert st.transition_observations==4+int(admissible)
    assert st.action_observations['clarify']==1+int(admissible)
    assert resolution['execution_receipt']['receipt_id']==str(receipt.receipt_id)
    assert all(v is False for k,v in resolution.items() if k.endswith('_authority'))
    assert st.pending_execution_receipt is None and st.pending_action==''
    assert runtime._resolve_pending_speech_act_outcome(result,event) is None
    assert runtime._resolve_pending_expression_outcome(result,event) is None


def test_receipt_persistence_failure_restores_state_and_security_checkpoint(runtime,monkeypatch):
    _,_,token,out=prepare(runtime)
    before=runtime.state.model_dump();checkpoint=runtime.security.restore().model_dump()
    monkeypatch.setattr(runtime.store,'append_state',Mock(side_effect=OSError('isolated database failure')))
    with pytest.raises(OSError,match='database failure'):transmit(runtime,token,out[0])
    assert runtime.state.model_dump()==before
    assert runtime.security.restore().model_dump()==checkpoint
    assert runtime._hf2_resolution_dispatch is None and runtime._hf2_receipt_to_mark is None


def arm_ingest(n,monkeypatch):
    n.state.cognition.language.dialogue.recent_referents=[
        cm.DialogueReferent(surface='Mira',kind='person'),cm.DialogueReferent(surface='Sara',kind='person')]
    actual=n._resolution_speech_act_selection
    seeded=False
    def capture(thought,result,**kwargs):
        nonlocal seeded
        assert result.state is n.state.math_kernel
        if not seeded:seed_test_geometry(n);seeded=True
        return actual(thought,result,**kwargs)
    monkeypatch.setattr(n,'_resolution_speech_act_selection',capture)


def test_ingest_prepares_only_and_rejected_next_ingress_invalidates_capability(runtime,monkeypatch):
    arm_ingest(runtime,monkeypatch)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-owner-test',content='She moved.',metadata={'owner_authenticated':True})
    reply=runtime.ingest(event,resolution_channel=CHANNEL)
    assert reply.text=='She: Sara / Mira?' and reply._resolution_dispatch is not None
    assert reply.speech_act_audit['execution_status']=='prepared-awaiting-asgi-send'
    assert runtime.state.cognition.speech_act_development.pending_action==''
    runtime.ingest(CognitiveEvent(kind=EventKind.USER_MESSAGE,source='test',content='rejected'),proposed_invariant_changes={'identity':'bad'})
    assert runtime._hf2_resolution_dispatch is None
    assert runtime.complete_resolution_dispatch(reply._resolution_dispatch,channel=CHANNEL,text_sha256=hashlib.sha256(reply.text.encode()).hexdigest())['receipt_recorded'] is False


def room_client(n,monkeypatch,*,loopback=True):
    import noeron.api as api
    from fastapi.testclient import TestClient
    from noeron.auth import OwnerAuthenticator
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
    auth=OwnerAuthenticator('isolated-m4c3c-bootstrap-token-no-deployment-secret',n.store)
    key=Ed25519PrivateKey.generate()
    public=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    auth.enroll_device('isolated-device','test',public,authority='isolated-owner-test')
    challenge=auth.challenge('isolated-device')
    signature=base64.b64encode(key.sign(challenge['message'].encode())).decode()
    session=auth.create_device_session('isolated-device',challenge['challenge_id'],signature)
    monkeypatch.setattr(api,'noeron',n);monkeypatch.setattr(api,'store',n.store);monkeypatch.setattr(api,'owner_auth',auth)
    client=TestClient(api.app,client=('127.0.0.1' if loopback else '203.0.113.10',50000))
    client.cookies.set(api._ROOM_COOKIE,session['session_token'])
    return client,auth


def test_real_authenticated_room_route_sends_and_receipts_without_voice_or_terra(runtime,monkeypatch):
    arm_ingest(runtime,monkeypatch)
    client,_=room_client(runtime,monkeypatch)
    monkeypatch.setattr(runtime.room,'present_native_utterance',Mock(side_effect=AssertionError('HTTP-only actuator')))
    monkeypatch.setattr(runtime.renderer,'render_audited',Mock(side_effect=AssertionError('no Terra authority')))
    before_owner=runtime.state.cognition.owner_relation.model_dump()
    response=client.post('/room/message',json={'content':'She moved.'})
    assert response.status_code==200
    payload=response.json()
    assert payload['text']==payload['english_text']=='She: Sara / Mira?'
    assert payload['communication_action']=='express' and payload['communication_native_choice_claim'] is True
    assert payload['native_presentation_created'] is False
    assert payload['internal_utterance_observation']['visibility_enabled'] is False
    st=runtime.state.cognition.speech_act_development
    assert st.pending_action=='clarify' and st.pending_execution_receipt.status=='asgi-response-body-sent'
    assert st.transition_observations==4 and st.operator_calibration_observations==0
    assert '_resolution_dispatch' not in response.text
    runtime.room.present_native_utterance.assert_not_called()
    runtime.renderer.render_audited.assert_not_called()
    assert st.pending_execution_receipt.peer_delivery_confirmed is False


@pytest.mark.parametrize('case',['missing','legacy','revoked','nonloopback'])
def test_room_auth_and_transport_boundaries_remain_in_force(runtime,monkeypatch,case):
    client,auth=room_client(runtime,monkeypatch,loopback=case!='nonloopback')
    if case=='missing':client.cookies.clear()
    elif case=='legacy':client.cookies.set('noeron_room_session','isolated-m4c3c-bootstrap-token-no-deployment-secret')
    elif case=='revoked':auth.revoke_device('isolated-device',authority='isolated-test')
    response=client.post('/room/message',json={'content':'She moved.'})
    assert response.status_code in (401,403)
    assert runtime.state.cognition.speech_act_development.action_observations=={}
    assert runtime.state.cognition.speech_act_development.pending_execution_receipt is None


def test_fresh_room_runtime_does_not_bootstrap_choice_or_fallback(runtime,monkeypatch):
    client,_=room_client(runtime,monkeypatch)
    runtime.state.cognition.language.dialogue.recent_referents=[cm.DialogueReferent(surface='Mira',kind='person'),cm.DialogueReferent(surface='Sara',kind='person')]
    response=client.post('/room/message',json={'content':'She moved.'})
    assert response.status_code==200 and response.json()['text']==''
    st=runtime.state.cognition.speech_act_development
    assert st.action_observations=={} and st.transition_observations==0
    assert st.pending_execution_receipt is None and st.last_execution_receipt is None


def test_native_proof_answer_keeps_existing_room_transport(runtime,monkeypatch):
    client,_=room_client(runtime,monkeypatch)
    runtime.state.cognition.language.owner_communication_controls.response_channel_override=True
    response=client.post('/room/message',json={'content':'Lamp is on. Is lamp on?'})
    assert response.status_code==200 and response.json()['text']=='Lamp is on.'
    assert runtime.state.math_kernel.reasoning.answer_candidates
    assert runtime.state.cognition.speech_act_development.last_execution_receipt is None
    assert runtime._hf2_resolution_dispatch is None
