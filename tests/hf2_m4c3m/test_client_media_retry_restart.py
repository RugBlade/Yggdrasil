from __future__ import annotations

import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest

from noeron.api import _ROOM_HTML
from noeron.memory import LocalEventStore
from tests.hf2_m4c3l.test_authenticated_client_playback_telemetry import (
    add_transport,
    make_native_audio,
    make_runtime,
    record,
)


def _client_fn() -> str:
    start = _ROOM_HTML.index('async function postClientMediaEvent')
    end = _ROOM_HTML.index('function configurePresentationAudio', start)
    return _ROOM_HTML[start:end]


def test_client_retries_network_uncertainty_with_same_payload_and_session_identity():
    fn = _client_fn()
    assert fn.index("const payload={") < fn.index('for(let attempt=0;attempt<10;attempt++)')
    assert "try{r=await fetch(" in fn
    assert "catch(e){if(attempt===9)throw e;await new Promise(resolve=>setTimeout(resolve,250));continue}" in fn
    assert "body:JSON.stringify(payload)" in fn
    assert "crypto.randomUUID()" not in fn


def test_client_retries_uncertain_body_read_but_not_explicit_non409_http_error():
    fn = _client_fn()
    assert "if(!r.ok&&r.status!==409)" in fn
    assert "let x;try{x=await r.json()}catch(e){if(attempt===9)throw e;await new Promise(resolve=>setTimeout(resolve,250));continue}" in fn
    assert "if(r.ok)return x;if(attempt===9)throw new Error(JSON.stringify(x));" in fn


def test_client_retry_change_does_not_add_autoplay_or_programmatic_play():
    assert "<audio autoplay" not in _ROOM_HTML
    assert "a.autoplay" not in _ROOM_HTML
    assert ".play()" not in _client_fn()


def test_uncertain_response_duplicates_remain_persistently_idempotent(tmp_path):
    n, store = make_runtime(tmp_path)
    p, a = make_native_audio(n, store)
    add_transport(n, p, a)
    sid = uuid4()

    first, first_created = record(n, p, a, event='playing', playback=sid, current=.2)
    second, second_created = record(n, p, a, event='playing', playback=sid, current=.9)
    assert first_created is True and second_created is False
    assert second.id == first.id and second.current_time_seconds == .2

    ended, ended_created = record(n, p, a, event='ended', playback=sid, current=1.0)
    ended_again, ended_again_created = record(n, p, a, event='ended', playback=sid, current=1.0)
    assert ended_created is True and ended_again_created is False
    assert ended_again.id == ended.id

    reopened = LocalEventStore(store.path)
    assert [r.event for r in reopened.native_audio_client_playback_receipts()] == ['playing', 'ended']


def test_rotated_session_or_other_device_cannot_close_prior_playback(tmp_path):
    n, store = make_runtime(tmp_path)
    p, a = make_native_audio(n, store)
    add_transport(n, p, a)
    sid = uuid4()
    record(n, p, a, event='playing', playback=sid, device='dev-1', fingerprint='fp-1', session='a' * 64)

    with pytest.raises(ValueError, match='prior playing'):
        record(n, p, a, event='ended', playback=sid, device='dev-1', fingerprint='fp-1', session='b' * 64)
    with pytest.raises(ValueError, match='prior playing'):
        record(n, p, a, event='ended', playback=sid, device='dev-2', fingerprint='fp-2', session='a' * 64)


def test_repeated_transport_receipts_do_not_create_extra_playback_sessions(tmp_path):
    n, store = make_runtime(tmp_path)
    p, a = make_native_audio(n, store)
    t1 = add_transport(n, p, a)
    t2 = add_transport(n, p, a)
    assert t1.id != t2.id
    assert store.native_audio_client_playback_receipts() == []

    playing, created = record(n, p, a, event='playing', playback=uuid4())
    assert created is True
    assert playing.transport_receipt_id == t2.id
    assert len(store.native_audio_client_playback_receipts()) == 1


def test_retry_and_duplicate_telemetry_never_changes_speech_act_state(tmp_path):
    n, store = make_runtime(tmp_path)
    p, a = make_native_audio(n, store)
    add_transport(n, p, a)
    sid = uuid4()
    before = n.state.cognition.speech_act_development.model_dump(mode='json')

    record(n, p, a, event='playing', playback=sid)
    record(n, p, a, event='playing', playback=sid)
    record(n, p, a, event='ended', playback=sid, current=1.0)
    record(n, p, a, event='ended', playback=sid, current=1.0)

    assert n.state.cognition.speech_act_development.model_dump(mode='json') == before


def test_true_process_restart_preserves_playing_dedupe_and_ended_sequence(tmp_path):
    db = tmp_path / 'restart.sqlite3'
    handoff = tmp_path / 'handoff.json'
    sid = str(uuid4())

    seed = r"""
import json, os, sys
from pathlib import Path
from uuid import UUID
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
from tests.hf2_m4c3l.test_authenticated_client_playback_telemetry import make_native_audio, add_transport
store=LocalEventStore(Path(sys.argv[1])); n=Noeron(MockLanguageEngine(),store,terra_enabled=False)
p,a=make_native_audio(n,store,b'RIFF-m4c3m-restart'); add_transport(n,p,a)
r,created=n.room.record_native_audio_client_playback_event(
 presentation_id=p.id,audio_artifact_id=a.id,owner_device_id='dev',owner_device_fingerprint='fp',
 owner_session_sha256='a'*64,playback_session_id=UUID(sys.argv[3]),event='playing',
 current_time_seconds=.2,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
Path(sys.argv[2]).write_text(json.dumps({'presentation':str(p.id),'artifact':str(a.id),'receipt':str(r.id)}))
os._exit(0)
"""
    check = r"""
import json, sys
from pathlib import Path
from uuid import UUID
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
store=LocalEventStore(Path(sys.argv[1])); n=Noeron(MockLanguageEngine(),store,terra_enabled=False)
h=json.loads(Path(sys.argv[2]).read_text()); p=store.native_presentation(h['presentation']); a=store.room_artifact(h['artifact']); sid=UUID(sys.argv[3])
before=n.state.cognition.speech_act_development.model_dump(mode='json')
r,c=n.room.record_native_audio_client_playback_event(
 presentation_id=p.id,audio_artifact_id=a.id,owner_device_id='dev',owner_device_fingerprint='fp',
 owner_session_sha256='a'*64,playback_session_id=sid,event='playing',
 current_time_seconds=.8,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
e,ec=n.room.record_native_audio_client_playback_event(
 presentation_id=p.id,audio_artifact_id=a.id,owner_device_id='dev',owner_device_fingerprint='fp',
 owner_session_sha256='a'*64,playback_session_id=sid,event='ended',
 current_time_seconds=1.0,duration_seconds=1.0,muted=False,volume=1.0,playback_rate=1.0)
after=n.state.cognition.speech_act_development.model_dump(mode='json')
print(json.dumps({'same':str(r.id)==h['receipt'],'duplicate_created':c,'ended_created':ec,
 'events':[x.event for x in store.native_audio_client_playback_receipts()],'speech_unchanged':before==after}))
"""
    env = os.environ.copy()
    first = subprocess.run([sys.executable, '-c', seed, str(db), str(handoff), sid], env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run([sys.executable, '-c', check, str(db), str(handoff), sid], env=env, capture_output=True, text=True, check=True)
    assert json.loads(second.stdout.strip()) == {
        'same': True,
        'duplicate_created': False,
        'ended_created': True,
        'events': ['playing', 'ended'],
        'speech_unchanged': True,
    }


def test_authority_boundary_remains_false_after_retry_semantics(tmp_path):
    n, store = make_runtime(tmp_path)
    p, a = make_native_audio(n, store)
    add_transport(n, p, a)
    receipt, _ = record(n, p, a, playback=uuid4())
    for name in (
        'audible_output_confirmed', 'peer_delivery_confirmed', 'peer_heard_confirmed',
        'peer_understanding_confirmed', 'peer_reply_causation_confirmed',
        'semantic_truth_authority', 'answer_authority', 'speech_act_choice_authority',
        'preference_label_authority', 'cognitive_memory_authority', 'relationship_authority',
        'source_write_authority', 'deployment_authority',
    ):
        assert getattr(receipt, name) is False
