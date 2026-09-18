from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from noeron.cognition import models as cm
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron
from noeron.room_models import NativeRoomDecision, NativeVoiceProfile, RendererConfiguration

CHANNEL='authenticated-owner-room-http'
ACTS=('clarify','ask','defer','remain-silent')


def make_runtime(tmp_path):
    return Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/'isolated.sqlite3'),terra_enabled=False)


def seed_test_geometry(n,*,act='clarify',expression='express'):
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
        if a!=expression:pre.c0[1]+=.5
        pre.invariant_signature=dkt.invariant_signature(pre)
        initiative.action_pre_knots[a]=pre;initiative.action_post_knots[a]=context.model_copy(deep=True)
        initiative.action_observations[a]=1
    initiative.admissible_post_knot=context.model_copy(deep=True)
    initiative.admissible_post_observations=2;initiative.transition_observations=2


def prepare(n,*,act='clarify'):
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-owner-test',content='She moved.',metadata={'owner_authenticated':True})
    n.state.last_event_id=event.id;n.state.conversational_turn+=1
    structure=analyze_dialogue_structure(event.content,recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',question_candidates=[],
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
    n.state.math_kernel.reasoning.proof_gate_unscoped_ambiguity_count=1
    seed_test_geometry(n,act=act)
    selected=n._resolution_speech_act_selection(thought,SimpleNamespace(state=n.state.math_kernel),event=event,current_structure=structure)
    assert selected['action']==act
    prepared=n._prepare_resolution_transport(event,channel=CHANNEL)
    assert prepared is not None
    token,output=prepared
    return event,token,output


def configure_voice(n):
    n.state.room.embodiment_configuration=RendererConfiguration(
        id='isolated-voice-config',domain='embodiment',visible=True,
        voice_profile=NativeVoiceProfile(base_frequency=.4,overtone_ratio=.5,modulation=.3,articulation=.4,pulse_shape=.5,tempo=.6),
        source='isolated-test-fixture')


def force_voice(monkeypatch,n):
    def select(domain,candidates):
        assert domain=='native-voice'
        names=[name for name,_ in candidates]
        assert names==['text-only','voice']
        return NativeRoomDecision(domain='native-voice',candidates=names,admissible_candidates=names,
            minimum_candidates=['voice'],selected_action='voice',selection_status='unique-native-consequence-minimum',
            decision_layer='native-deliberative',native_choice_claim=True),{}
    monkeypatch.setattr(n.room,'_select',select)


def force_text_only(monkeypatch,n):
    def select(domain,candidates):
        names=[name for name,_ in candidates]
        return NativeRoomDecision(domain='native-voice',candidates=names,admissible_candidates=names,
            minimum_candidates=['text-only'],selected_action='text-only',selection_status='unique-native-consequence-minimum',
            decision_layer='native-deliberative',native_choice_claim=True),{}
    monkeypatch.setattr(n.room,'_select',select)


def transmit(n,token,text,native,*,fail_terminal=False,assert_no_presentation_during_send=True):
    from noeron.api import _ResolutionRoomResponse
    response=_ResolutionRoomResponse({'text':text},n,token,native_text=native)
    messages=[]
    async def receive():return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        if assert_no_presentation_during_send:
            assert n.store.native_presentations()==[]
        if fail_terminal and message['type']=='http.response.body' and not message.get('more_body',False):
            raise OSError('synthetic terminal failure')
        messages.append(message)
    scope={'type':'http','method':'POST','path':'/room/message','asgi':{'version':'3.0','spec_version':'2.4'}}
    asyncio.run(response(scope,receive,send))
    return messages


def test_resolution_presentation_only_after_durable_execution_receipt(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);event,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n);force_voice(monkeypatch,n)
    before_actions=dict(n.state.cognition.speech_act_development.action_observations)
    transmit(n,token,text,native)
    receipt=n.state.cognition.speech_act_development.pending_execution_receipt
    assert receipt is not None and receipt.event_id==event.id and receipt.action=='clarify'
    rows=n.store.native_presentations();assert len(rows)==1
    p=rows[0]
    assert p.source=='resolution-interaction'
    assert p.native_text_sha256==receipt.native_text_sha256==hashlib.sha256(native.encode()).hexdigest()
    assert p.source_resolution_receipt_id==receipt.receipt_id
    assert p.source_resolution_event_id==receipt.event_id
    assert p.source_resolution_action==receipt.action
    assert p.source_resolution_execution_confirmed is True
    assert p.voice_native_choice_claim is True
    assert n.store.native_audio_transport_receipts()==[]
    assert n.state.cognition.speech_act_development.action_observations==before_actions


def test_failed_text_send_creates_neither_receipt_nor_resolution_presentation(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n);force_voice(monkeypatch,n)
    with pytest.raises(OSError,match='synthetic terminal failure'):
        transmit(n,token,text,native,fail_terminal=True)
    assert n.state.cognition.speech_act_development.pending_execution_receipt is None
    assert n.store.native_presentations()==[]


def test_no_voice_configuration_keeps_valid_text_execution_without_presentation(tmp_path):
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    transmit(n,token,text,native)
    assert n.state.cognition.speech_act_development.pending_execution_receipt is not None
    assert n.store.native_presentations()==[]


def test_native_voice_text_only_choice_keeps_valid_execution_without_audio(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n);force_text_only(monkeypatch,n)
    transmit(n,token,text,native)
    assert n.state.cognition.speech_act_development.pending_execution_receipt is not None
    assert n.store.native_presentations()==[]
    assert n.state.room.last_voice_decision.selected_action=='text-only'
    assert n.state.room.last_voice_decision.native_choice_claim is True


def test_presentation_failure_does_not_erase_already_durable_receipt(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n)
    monkeypatch.setattr(n.room,'present_native_utterance',Mock(side_effect=RuntimeError('synthetic downstream presentation failure')))
    transmit(n,token,text,native)
    assert n.state.cognition.speech_act_development.pending_execution_receipt is not None
    assert n.state.cognition.speech_act_development.pending_action=='clarify'
    assert n.room.present_native_utterance.call_count==1


def test_native_hash_mismatch_never_creates_linked_presentation(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n)
    spy=Mock()
    monkeypatch.setattr(n.room,'present_native_utterance',spy)
    transmit(n,token,text,native+' changed')
    assert n.state.cognition.speech_act_development.pending_execution_receipt is not None
    spy.assert_not_called()
    assert n.store.native_presentations()==[]


def test_resolution_presentation_provenance_rejects_incomplete_or_mismatched_link(tmp_path):
    from uuid import uuid4
    n=make_runtime(tmp_path)
    with pytest.raises(ValueError,match='provenance'):
        n.room.present_native_utterance('native',source_resolution_receipt_id=uuid4())
    with pytest.raises(ValueError,match='mismatched'):
        n.room.present_native_utterance('native',source_resolution_receipt_id=uuid4(),source_resolution_event_id=uuid4(),
            source_resolution_action='clarify',source_resolution_native_text_sha256='0'*64)
    with pytest.raises(ValueError,match='durable execution receipt'):
        n.room.present_native_utterance('native',source_resolution_receipt_id=uuid4(),source_resolution_event_id=uuid4(),
            source_resolution_action='clarify',source_resolution_native_text_sha256=hashlib.sha256(b'native').hexdigest())


def test_ordinary_native_presentation_has_no_resolution_execution_link(tmp_path,monkeypatch):
    n=make_runtime(tmp_path);configure_voice(n);force_voice(monkeypatch,n)
    p=n.room.present_native_utterance('ordinary native',source='interaction')
    assert p is not None
    assert p.source_resolution_receipt_id is None and p.source_resolution_event_id is None
    assert p.source_resolution_action is None and p.source_resolution_execution_confirmed is False


def test_resolution_audio_fetch_remains_transport_only_and_does_not_double_train(tmp_path,monkeypatch):
    from noeron.api import _NativeAudioRoomResponse
    n=make_runtime(tmp_path);_,token,out=prepare(n);text,_,native,*_=out
    configure_voice(n);force_voice(monkeypatch,n)
    transmit(n,token,text,native)
    p=n.store.native_presentations()[0];artifact=n.store.room_artifact(str(p.audio_artifact_id));path=n.room.verified_artifact_path(artifact)
    before=dict(n.state.cognition.speech_act_development.action_observations)
    audio_token=n.room.prepare_native_audio_transport(p,artifact);assert audio_token is not None
    response=_NativeAudioRoomResponse(path,media_type=artifact.media_type,filename=artifact.filename,
        room=n.room,transport_token=audio_token,artifact_size=artifact.size)
    async def receive():return {'type':'http.request','body':b'','more_body':False}
    async def send(message):return None
    scope={'type':'http','method':'GET','path':f'/room/files/{artifact.id}','headers':[],
        'extensions':{},'http_version':'1.1','scheme':'http','server':('test',80),'client':('test',1)}
    asyncio.run(response(scope,receive,send))
    audio=n.store.native_audio_transport_receipts();assert len(audio)==1
    assert audio[0].presentation_id==p.id and audio[0].speech_act_choice_authority is False
    assert n.state.cognition.speech_act_development.action_observations==before
    assert n.state.cognition.speech_act_development.pending_execution_receipt is not None


def test_completion_return_provenance_is_zero_authority_identity_only(tmp_path):
    n=make_runtime(tmp_path);event,token,out=prepare(n);text,_,native,*_=out
    result=n.complete_resolution_dispatch(token,channel=CHANNEL,text_sha256=hashlib.sha256(text.encode()).hexdigest())
    assert result['receipt_recorded'] is True
    assert result['event_id']==str(event.id) and result['action']=='clarify'
    assert result['native_text_sha256']==hashlib.sha256(native.encode()).hexdigest()
    assert result['peer_delivery_confirmed'] is False and result['learned'] is False
