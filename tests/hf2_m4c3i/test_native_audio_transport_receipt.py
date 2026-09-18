from __future__ import annotations

import asyncio
from hashlib import sha256

import pytest

from noeron.api import _NativeAudioRoomResponse
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
from noeron.room_models import NativePresentationRecord, NativeRoomDecision


def make_runtime(tmp_path):
    store=LocalEventStore(tmp_path/'audio.sqlite3')
    n=Noeron(MockLanguageEngine(),store,terra_enabled=False)
    return n,store


def make_native_audio(n,store,data=b'RIFF-native-audio-test-bytes'):
    decision=NativeRoomDecision(
        domain='native-voice',selected_action='voice',selection_status='selected-unique-native-minimum',
        decision_layer='native-deliberative',native_choice_claim=True,
    )
    artifact=n.room._publish_bytes(data,'native-test.wav','audio/wav',decision,
        expected_domain='native-voice',expected_action='voice')
    presentation=NativePresentationRecord(
        source='test',native_text_sha256=sha256(b'native-test').hexdigest(),native_text_private='native-test',
        audio_artifact_id=artifact.id,audio_sha256=artifact.sha256,voice_native_choice_claim=True,
        voice_decision_id=decision.id,
    )
    store.append_native_presentation(presentation)
    return presentation,artifact,n.room.verified_artifact_path(artifact),data


def response_for(n,presentation,artifact,path):
    token=n.room.prepare_native_audio_transport(presentation,artifact)
    assert token is not None
    return _NativeAudioRoomResponse(path,media_type=artifact.media_type,filename=artifact.filename,
        headers={'Cache-Control':'no-store'},room=n.room,transport_token=token,artifact_size=artifact.size),token


def run_response(response,artifact_id,*,method='GET',headers=None,extensions=None,fail_terminal=False):
    sent=[]
    async def receive():
        return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        if fail_terminal and ((message['type']=='http.response.body' and not message.get('more_body',False)) or message['type']=='http.response.pathsend'):
            raise RuntimeError('synthetic send failure')
        sent.append(message)
    scope={'type':'http','method':method,'path':f'/room/files/{artifact_id}','headers':headers or [],
        'extensions':extensions or {},'http_version':'1.1','scheme':'http','server':('test',80),'client':('test',1)}
    asyncio.run(response(scope,receive,send))
    return sent


def test_artifact_and_presentation_existence_alone_create_no_transport_receipt(tmp_path):
    n,store=make_runtime(tmp_path);make_native_audio(n,store)
    assert store.native_audio_transport_receipts()==[]


def test_full_audio_body_send_records_nonsemantic_receipt(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,data=make_native_audio(n,store)
    before=dict(n.state.cognition.speech_act_development.action_observations)
    before_t=n.state.cognition.speech_act_development.transition_observations
    response,_=response_for(n,p,a,path);run_response(response,a.id)
    rows=store.native_audio_transport_receipts();assert len(rows)==1
    r=rows[0]
    assert r.presentation_id==p.id and r.audio_artifact_id==a.id
    assert r.audio_sha256==a.sha256 and r.native_text_sha256==p.native_text_sha256
    assert r.http_status==200 and r.response_bytes==len(data)
    assert r.complete_artifact_single_response is True and r.pathsend_used is False
    assert r.playback_confirmed is r.peer_delivery_confirmed is r.peer_heard_confirmed is False
    assert r.peer_understanding_confirmed is r.peer_reply_causation_confirmed is False
    assert r.semantic_truth_authority is r.answer_authority is r.speech_act_choice_authority is False
    assert r.preference_label_authority is r.cognitive_memory_authority is r.relationship_authority is False
    assert r.source_write_authority is r.deployment_authority is False
    assert n.state.cognition.speech_act_development.action_observations==before
    assert n.state.cognition.speech_act_development.transition_observations==before_t


def test_pathsend_completion_records_exact_artifact_size_without_playback_claim(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,data=make_native_audio(n,store)
    response,_=response_for(n,p,a,path)
    sent=run_response(response,a.id,extensions={'http.response.pathsend':{}})
    assert any(m['type']=='http.response.pathsend' for m in sent)
    r=store.native_audio_transport_receipts()[0]
    assert r.http_status==200 and r.response_bytes==len(data)
    assert r.pathsend_used is True and r.complete_artifact_single_response is True
    assert r.playback_confirmed is False and r.peer_heard_confirmed is False


def test_range_send_records_partial_transport_not_full_artifact_claim(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,data=make_native_audio(n,store)
    response,_=response_for(n,p,a,path)
    run_response(response,a.id,headers=[(b'range',b'bytes=0-3')])
    r=store.native_audio_transport_receipts()[0]
    assert r.http_status==206 and r.response_bytes==4
    assert r.content_range==f'bytes 0-3/{len(data)}'
    assert r.complete_artifact_single_response is False
    assert r.peer_delivery_confirmed is r.peer_heard_confirmed is False


def test_head_request_does_not_create_audio_transport_receipt(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,_=make_native_audio(n,store)
    response,_=response_for(n,p,a,path);run_response(response,a.id,method='HEAD')
    assert store.native_audio_transport_receipts()==[]
    assert n.room._native_audio_transports=={}


def test_failed_terminal_send_creates_no_receipt_and_consumes_capability(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,_=make_native_audio(n,store)
    response,_=response_for(n,p,a,path)
    with pytest.raises(RuntimeError,match='synthetic send failure'):
        run_response(response,a.id,fail_terminal=True)
    assert store.native_audio_transport_receipts()==[]
    assert n.room._native_audio_transports=={}


def test_mismatched_or_owner_to_noeron_artifact_cannot_prepare_receipt(tmp_path):
    n,store=make_runtime(tmp_path);p,a,_,_=make_native_audio(n,store)
    other=n.room.store_owner_file(b'owner-audio','owner.wav','audio/wav')
    assert n.room.prepare_native_audio_transport(p,other) is None
    p2=p.model_copy(deep=True);p2.audio_sha256='0'*64
    assert n.room.prepare_native_audio_transport(p2,a) is None


def test_transport_capability_is_single_use(tmp_path):
    n,store=make_runtime(tmp_path);p,a,_,_=make_native_audio(n,store)
    token=n.room.prepare_native_audio_transport(p,a);assert token is not None
    first=n.room.complete_native_audio_transport(token,http_status=200,response_bytes=a.size)
    second=n.room.complete_native_audio_transport(token,http_status=200,response_bytes=a.size)
    assert first is not None and second is None
    assert len(store.native_audio_transport_receipts())==1


def test_repeated_authenticated_fetches_are_distinct_transport_receipts_not_preferences(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,_=make_native_audio(n,store)
    before=dict(n.state.cognition.speech_act_development.action_observations)
    for _ in range(2):
        response,_=response_for(n,p,a,path);run_response(response,a.id)
    rows=store.native_audio_transport_receipts();assert len(rows)==2 and rows[0].id!=rows[1].id
    assert n.state.cognition.speech_act_development.action_observations==before
    assert all(not r.preference_label_authority and not r.relationship_authority for r in rows)


def test_transport_receipt_is_separate_from_decoder_and_native_voice_choice(tmp_path):
    n,store=make_runtime(tmp_path);p,a,path,_=make_native_audio(n,store)
    response,_=response_for(n,p,a,path);run_response(response,a.id)
    r=store.native_audio_transport_receipts()[0]
    assert p.voice_native_choice_claim is True
    assert p.decoder_cognitive_authority is p.decoder_realization_authority is False
    assert r.speech_act_choice_authority is False and r.cognitive_memory_authority is False
