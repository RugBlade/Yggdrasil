from __future__ import annotations

import inspect
from hashlib import sha256
from uuid import uuid4

import pytest
from pydantic import ValidationError

from noeron.api import _ROOM_HTML, RoomNativeAudioClientPlaybackRequest, _room_snapshot
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
from noeron.room_models import (
    NativeAudioClientPlaybackTelemetryReceipt,
    NativePresentationRecord,
    NativeRoomDecision,
)


def make_runtime(tmp_path, name='client-playback.sqlite3'):
    store=LocalEventStore(tmp_path/name)
    n=Noeron(MockLanguageEngine(),store,terra_enabled=False)
    return n,store


def make_native_audio(n,store,data=b'RIFF-m4c3l-native-audio'):
    decision=NativeRoomDecision(
        domain='native-voice',selected_action='voice',selection_status='selected-unique-native-minimum',
        decision_layer='native-deliberative',native_choice_claim=True,
    )
    artifact=n.room._publish_bytes(data,'native-m4c3l.wav','audio/wav',decision,
        expected_domain='native-voice',expected_action='voice')
    presentation=NativePresentationRecord(
        source='m4c3l-test',native_text_sha256=sha256(b'native-m4c3l').hexdigest(),native_text_private='native-m4c3l',
        audio_artifact_id=artifact.id,audio_sha256=artifact.sha256,voice_native_choice_claim=True,
        voice_decision_id=decision.id,
    )
    store.append_native_presentation(presentation)
    return presentation,artifact


def add_transport(n,p,a):
    token=n.room.prepare_native_audio_transport(p,a);assert token is not None
    r=n.room.complete_native_audio_transport(token,http_status=200,response_bytes=a.size)
    assert r is not None
    return r


def record(n,p,a,*,event='playing',device='owner-device-1',fingerprint='fp-1',session='a'*64,playback=None,current=0.25):
    return n.room.record_native_audio_client_playback_event(
        presentation_id=p.id,audio_artifact_id=a.id,owner_device_id=device,
        owner_device_fingerprint=fingerprint,owner_session_sha256=session,
        playback_session_id=playback or uuid4(),event=event,current_time_seconds=current,
        duration_seconds=1.0,muted=False,volume=.8,playback_rate=1.0,
    )


def test_typed_client_media_receipt_cannot_claim_audible_hearing_or_authority():
    base=dict(presentation_id=uuid4(),audio_artifact_id=uuid4(),transport_receipt_id=uuid4(),
        native_text_sha256='1'*64,audio_sha256='2'*64,owner_device_id='dev',owner_device_fingerprint='fp',
        owner_session_sha256='3'*64,playback_session_id=uuid4(),event='playing',current_time_seconds=0)
    r=NativeAudioClientPlaybackTelemetryReceipt(**base)
    assert r.client_media_event_received is True
    assert r.audible_output_confirmed is r.peer_delivery_confirmed is r.peer_heard_confirmed is False
    assert r.peer_understanding_confirmed is r.peer_reply_causation_confirmed is False
    assert r.semantic_truth_authority is r.answer_authority is r.speech_act_choice_authority is False
    assert r.preference_label_authority is r.cognitive_memory_authority is r.relationship_authority is False
    assert r.source_write_authority is r.deployment_authority is False
    for field in ('audible_output_confirmed','peer_heard_confirmed','relationship_authority','speech_act_choice_authority'):
        with pytest.raises(ValidationError):
            NativeAudioClientPlaybackTelemetryReceipt(**base,**{field:True})


def test_playing_requires_exact_presentation_artifact_and_durable_transport(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store)
    with pytest.raises(ValueError,match='transport provenance'):
        record(n,p,a)
    add_transport(n,p,a)
    bad=a.model_copy(deep=True);bad.id=uuid4();store.append_room_artifact(bad)
    with pytest.raises(ValueError,match='presentation/artifact provenance'):
        record(n,p,bad)


def test_playing_records_authenticated_client_media_event_only(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);tr=add_transport(n,p,a);sid=uuid4()
    before=dict(n.state.cognition.speech_act_development.action_observations)
    before_t=n.state.cognition.speech_act_development.transition_observations
    r,created=record(n,p,a,playback=sid)
    assert created is True and r.event=='playing' and r.transport_receipt_id==tr.id
    assert r.owner_device_id=='owner-device-1' and r.owner_session_sha256=='a'*64
    assert r.client_media_event_received is True and r.audible_output_confirmed is False
    assert store.native_audio_client_playback_receipts()==[r]
    assert n.state.cognition.speech_act_development.action_observations==before
    assert n.state.cognition.speech_act_development.transition_observations==before_t


def test_duplicate_playing_is_persistently_idempotent_even_if_metrics_differ(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a);sid=uuid4()
    first,created1=record(n,p,a,playback=sid,current=.2)
    second,created2=record(n,p,a,playback=sid,current=.7)
    assert created1 is True and created2 is False
    assert second.id==first.id and second.current_time_seconds==first.current_time_seconds==.2
    assert len(store.native_audio_client_playback_receipts())==1
    reopened=LocalEventStore(store.path)
    rows=reopened.native_audio_client_playback_receipts()
    assert len(rows)==1 and rows[0].id==first.id


def test_ended_requires_prior_playing_same_device_and_exact_room_session(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a);sid=uuid4()
    with pytest.raises(ValueError,match='prior playing'):
        record(n,p,a,event='ended',playback=sid)
    record(n,p,a,event='playing',playback=sid)
    with pytest.raises(ValueError,match='prior playing'):
        record(n,p,a,event='ended',playback=sid,device='owner-device-2',fingerprint='fp-2')
    with pytest.raises(ValueError,match='prior playing'):
        record(n,p,a,event='ended',playback=sid,session='b'*64)
    ended,created=record(n,p,a,event='ended',playback=sid,current=1.0)
    assert created is True and ended.event=='ended'
    assert ended.transport_receipt_id==store.native_audio_client_playback_receipts()[0].transport_receipt_id


def test_duplicate_ended_is_idempotent_and_does_not_train(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a);sid=uuid4()
    record(n,p,a,event='playing',playback=sid)
    before=dict(n.state.cognition.speech_act_development.action_observations);before_t=n.state.cognition.speech_act_development.transition_observations
    first,c1=record(n,p,a,event='ended',playback=sid,current=1.0)
    second,c2=record(n,p,a,event='ended',playback=sid,current=1.0)
    assert c1 is True and c2 is False and first.id==second.id
    assert len(store.native_audio_client_playback_receipts())==2
    assert n.state.cognition.speech_act_development.action_observations==before
    assert n.state.cognition.speech_act_development.transition_observations==before_t


def test_ended_keeps_original_playing_transport_link_even_after_new_fetch(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);first_transport=add_transport(n,p,a);sid=uuid4()
    playing,_=record(n,p,a,event='playing',playback=sid)
    assert playing.transport_receipt_id==first_transport.id
    second_transport=add_transport(n,p,a);assert second_transport.id!=first_transport.id
    ended,_=record(n,p,a,event='ended',playback=sid,current=1.0)
    assert ended.transport_receipt_id==first_transport.id


def test_request_schema_has_no_client_submitted_authority_or_hearing_fields():
    fields=set(RoomNativeAudioClientPlaybackRequest.model_fields)
    assert fields=={'audio_artifact_id','playback_session_id','event','current_time_seconds','duration_seconds','muted','volume','playback_rate'}
    assert not ({'peer_heard_confirmed','audible_output_confirmed','speech_act_choice_authority','preference_label_authority','relationship_authority'} & fields)


def test_room_client_has_no_native_audio_autoplay_and_uses_playing_then_ended():
    html=_ROOM_HTML
    assert "a.addEventListener('playing'" in html
    assert "a.addEventListener('ended'" in html
    assert "a.addEventListener('play'" not in html
    assert 'a.autoplay' not in html
    assert '<audio autoplay' not in html
    assert "a.preload='metadata'" in html


def test_room_client_reconciles_presentation_nodes_without_generic_view_recreation():
    html=_ROOM_HTML
    assert "const presentations=document.getElementById('presentations')" in html
    assert 'const presentationNodes=new Map()' in html
    assert 'function reconcilePresentations(rows)' in html
    assert 'reconcilePresentations(s.native_presentations)' in html
    assert "view.innerHTML=''" in html
    assert "presentations.innerHTML=''" not in html
    assert "for(const p of s.native_presentations){let d=document.createElement('div')" not in html
    assert "entry.audio.dataset.artifactId!==p.audio_artifact_id" in html


def test_client_telemetry_retry_preserves_same_origin_identity_across_compatible_retry_contracts():
    html=_ROOM_HTML
    assert "credentials:'same-origin'" in html
    legacy_retry = "if(r.status!==409||attempt===9)" in html
    network_uncertainty_retry = (
        "if(!r.ok&&r.status!==409)" in html
        and "if(r.ok)return x;if(attempt===9)" in html
    )
    assert legacy_retry or network_uncertainty_retry
    assert "playback_session_id:playbackSessionId" in html
    assert "crypto.randomUUID()" in html


def test_snapshot_sanitization_does_not_expose_owner_session_hash():
    src=inspect.getsource(_room_snapshot)
    assert 'native_audio_client_playback_receipts' in src
    assert 'owner_device_id' in src
    assert 'owner_session_sha256' not in src
    assert "'audible_output_confirmed':False" in src
    assert "'peer_heard_confirmed':False" in src


def test_invalid_client_event_or_session_provenance_fails_closed(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a)
    with pytest.raises(ValueError,match='playing or ended'):
        record(n,p,a,event='play')
    with pytest.raises(ValueError,match='device/session provenance'):
        record(n,p,a,device='')
    with pytest.raises(ValueError,match='device/session provenance'):
        record(n,p,a,session='short')


def test_client_telemetry_journal_is_zero_authority_and_only_created_once(tmp_path):
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a);sid=uuid4()
    r,c1=record(n,p,a,playback=sid);r2,c2=record(n,p,a,playback=sid)
    assert c1 is True and c2 is False and r.id==r2.id
    entries=[x for x in store.room_journal(200) if x.kind=='native-audio-client-media-event']
    assert len(entries)==1
    payload=entries[0].payload
    assert payload['client_media_event_received'] is True
    assert payload['audible_output_confirmed'] is payload['peer_heard_confirmed'] is False
    assert payload['cognitive_authority'] is payload['speech_act_choice_authority'] is False
    assert payload['preference_label_authority'] is payload['relationship_authority'] is False


def _real_device_session(store):
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from noeron.auth import OwnerAuthenticator
    private=Ed25519PrivateKey.generate()
    raw=private.public_key().public_bytes(encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
    auth=OwnerAuthenticator('',store,legacy_enabled=False)
    auth.enroll_device('m4c3l-device','M4C3L test',base64.b64encode(raw).decode(),authority='isolated-test')
    challenge=auth.challenge('m4c3l-device')
    sig=base64.b64encode(private.sign(challenge['message'].encode())).decode()
    session=auth.create_device_session('m4c3l-device',challenge['challenge_id'],sig)
    return auth,session


def _room_request(token,host='127.0.0.1'):
    from starlette.requests import Request
    from noeron.api import _ROOM_COOKIE
    return Request({'type':'http','method':'POST','path':'/room/native/presentations/x/client-playback',
        'headers':[(b'cookie',f'{_ROOM_COOKIE}={token}'.encode())],'client':(host,12345),
        'server':('127.0.0.1',8741),'scheme':'http','query_string':b''})


def test_endpoint_uses_real_ed25519_room_session_and_returns_sanitized_receipt(tmp_path,monkeypatch):
    import noeron.api as api
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a)
    auth,session=_real_device_session(store)
    monkeypatch.setattr(api,'noeron',n);monkeypatch.setattr(api,'store',store);monkeypatch.setattr(api,'owner_auth',auth)
    req=RoomNativeAudioClientPlaybackRequest(audio_artifact_id=a.id,playback_session_id=uuid4(),event='playing',
        current_time_seconds=.1,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
    out=api.room_native_audio_client_playback(str(p.id),req,_room_request(session['session_token']))
    assert out['created'] is True and out['event']=='playing'
    assert out['owner_device_id']=='m4c3l-device'
    assert out['client_media_event_received'] is True and out['audible_output_confirmed'] is False
    assert out['peer_heard_confirmed'] is out['peer_understanding_confirmed'] is False
    assert 'owner_session_sha256' not in out and 'owner_device_fingerprint' not in out


def test_endpoint_rejects_legacy_bootstrap_even_when_legacy_token_is_valid(tmp_path,monkeypatch):
    import noeron.api as api
    from fastapi import HTTPException
    from noeron.auth import OwnerAuthenticator
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a)
    auth=OwnerAuthenticator('legacy-secret',store,legacy_enabled=True)
    monkeypatch.setattr(api,'noeron',n);monkeypatch.setattr(api,'store',store);monkeypatch.setattr(api,'owner_auth',auth)
    req=RoomNativeAudioClientPlaybackRequest(audio_artifact_id=a.id,playback_session_id=uuid4(),event='playing',
        current_time_seconds=.1,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
    with pytest.raises(HTTPException) as exc:
        api.room_native_audio_client_playback(str(p.id),req,_room_request('legacy-secret'))
    assert exc.value.status_code==401


def test_endpoint_rejects_nonprivate_transport_even_with_valid_device_session(tmp_path,monkeypatch):
    import noeron.api as api
    from fastapi import HTTPException
    n,store=make_runtime(tmp_path);p,a=make_native_audio(n,store);add_transport(n,p,a)
    auth,session=_real_device_session(store)
    monkeypatch.setattr(api,'noeron',n);monkeypatch.setattr(api,'store',store);monkeypatch.setattr(api,'owner_auth',auth)
    req=RoomNativeAudioClientPlaybackRequest(audio_artifact_id=a.id,playback_session_id=uuid4(),event='playing',
        current_time_seconds=.1,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
    with pytest.raises(HTTPException) as exc:
        api.room_native_audio_client_playback(str(p.id),req,_room_request(session['session_token'],host='198.51.100.7'))
    assert exc.value.status_code==403
