"""M4C3K true process-crash verification for post-receipt native presentation.

All hard exits run in disposable child processes against isolated SQLite databases.
Synthetic speech-act/expression/voice geometry is test-only and does not seed product defaults.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CHILD = r'''
import asyncio,os,sys
from pathlib import Path
from noeron.cognition import models as cm
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind
from noeron.orchestrator import Noeron
from noeron.room_models import NativeRoomDecision,NativeVoiceProfile,RendererConfiguration

phase,dbs,marker_dir=sys.argv[1:4]
db=Path(dbs);markers=Path(marker_dir);markers.mkdir(parents=True,exist_ok=True)

def seed_resolution_geometry(n,target='clarify'):
    context=n.state.math_kernel.dkt.core_knot
    st=n.state.cognition.speech_act_development
    for i,action in enumerate(('clarify','ask','defer','remain-silent'),1):
        pre=context.model_copy(deep=True)
        if action!=target:pre.c0[0]+=i*0.2
        pre.invariant_signature=dkt.invariant_signature(pre)
        st.action_pre_knots[action]=pre
        st.action_post_knots[action]=context.model_copy(deep=True)
        st.action_observations[action]=1
    st.transition_observations=4

def seed_expression_geometry(n):
    context=n.state.math_kernel.dkt.core_knot
    st=n.state.cognition.initiative_development
    for action in ('express','continue-private'):
        pre=context.model_copy(deep=True)
        if action!='express':pre.c0[1]+=0.5
        pre.invariant_signature=dkt.invariant_signature(pre)
        st.action_pre_knots[action]=pre
        st.action_post_knots[action]=context.model_copy(deep=True)
        st.action_observations[action]=1
    st.admissible_post_knot=context.model_copy(deep=True)
    st.admissible_post_observations=2
    st.transition_observations=2

def arm(n):
    actual=n._resolution_speech_act_selection
    seeded=False
    def wrapped(thought,result,**kwargs):
        nonlocal seeded
        if not seeded:
            seed_resolution_geometry(n)
            seed_expression_geometry(n)
            seeded=True
        return actual(thought,result,**kwargs)
    n._resolution_speech_act_selection=wrapped

def force_native_voice(n):
    def select(domain,candidates):
        assert domain=='native-voice'
        names=[name for name,_ in candidates]
        rec=NativeRoomDecision(
            domain='native-voice',candidates=names,admissible_candidates=names,
            minimum_candidates=['voice'],selected_action='voice',
            selection_status='unique-native-consequence-minimum',
            decision_layer='native-deliberative',native_choice_claim=True,
        )
        return rec,{}
    n.room._select=select

n=Noeron(MockLanguageEngine(),LocalEventStore(db),terra_enabled=False)
n.state.cognition.language.dialogue.recent_referents=[
    cm.DialogueReferent(surface='Mira',kind='person'),
    cm.DialogueReferent(surface='Sara',kind='person'),
]
n.state.room.embodiment_configuration=RendererConfiguration(
    id='m4c3k-test-voice',domain='embodiment',visible=True,
    voice_profile=NativeVoiceProfile(
        base_frequency=.4,overtone_ratio=.5,modulation=.3,
        articulation=.4,pulse_shape=.5,tempo=.6,
    ),
    source='m4c3k-isolated-test-fixture',
)
n.store.append_state(n.state)
arm(n);force_native_voice(n)
event=CognitiveEvent(
    kind=EventKind.USER_MESSAGE,source='m4c3k-origin',
    content='She moved.',metadata={'owner_authenticated':True},
)
reply=n.ingest(event,resolution_channel='authenticated-owner-room-http')
assert reply._resolution_dispatch is not None and reply.native_text
(markers/'prepared').write_text(str(event.id))

if phase=='after-receipt-before-presentation':
    def crash_present(*args,**kwargs):
        receipt=n.state.cognition.speech_act_development.pending_execution_receipt
        assert receipt is not None
        (markers/'receipt-durable').write_text(str(receipt.receipt_id))
        os._exit(80)
    n.room.present_native_utterance=crash_present
elif phase=='after-voice-before-artifact':
    def crash_publish(*args,**kwargs):
        rec=n.state.room.last_voice_decision
        assert rec is not None and rec.native_choice_claim and rec.selected_action=='voice'
        (markers/'voice-selected').write_text(str(rec.id))
        os._exit(81)
    n.room._publish_bytes=crash_publish
elif phase=='after-artifact-before-presentation':
    real_publish=n.room._publish_bytes
    def crash_after_publish(*args,**kwargs):
        artifact=real_publish(*args,**kwargs)
        (markers/'artifact-durable').write_text(str(artifact.id))
        os._exit(82)
    n.room._publish_bytes=crash_after_publish
elif phase=='after-presentation-before-followup':
    real_append=n.store.append_native_presentation
    def crash_after_presentation(rec):
        real_append(rec)
        (markers/'presentation-durable').write_text(str(rec.id))
        os._exit(83)
    n.store.append_native_presentation=crash_after_presentation
else:
    raise SystemExit('bad phase')

from noeron.api import _ResolutionRoomResponse
response=_ResolutionRoomResponse(
    {'text':reply.text},n,reply._resolution_dispatch,native_text=reply.native_text,
)
async def receive():
    return {'type':'http.request','body':b'','more_body':False}
async def send(message):
    return None
asyncio.run(response(
    {'type':'http','method':'POST','path':'/room/message',
     'asgi':{'version':'3.0','spec_version':'2.4'}},
    receive,send,
))
raise SystemExit('crash phase did not crash')
'''

INSPECT = r'''
import asyncio,json,sys
from datetime import timedelta
from pathlib import Path
from noeron.api import _NativeAudioRoomResponse
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind
from noeron.orchestrator import Noeron

db=Path(sys.argv[1]);op=sys.argv[2]
n=Noeron(MockLanguageEngine(),LocalEventStore(db),terra_enabled=False)
st=n.state.cognition.speech_act_development
receipt=st.pending_execution_receipt
before_actions=dict(st.action_observations)
before_trans=int(st.transition_observations)
extra={}

if op=='consume':
    event=CognitiveEvent(
        kind=EventKind.USER_MESSAGE,source='m4c3k-later',
        content='Mira moved book.',
        created_at=(receipt.completed_at+timedelta(seconds=2) if receipt else None),
    ) if receipt else CognitiveEvent(
        kind=EventKind.USER_MESSAGE,source='m4c3k-later',content='Mira moved book.',
    )
    n.ingest(event)
    extra={
        'action_delta':{
            k:int(st.action_observations.get(k,0))-int(before_actions.get(k,0))
            for k in set(before_actions)|set(st.action_observations)
        },
        'transition_delta':int(st.transition_observations)-before_trans,
    }
elif op=='fetch-audio':
    presentations=n.store.native_presentations()
    assert len(presentations)==1
    p=presentations[0]
    artifact=n.store.room_artifact(str(p.audio_artifact_id))
    assert artifact is not None
    token=n.room.prepare_native_audio_transport(p,artifact)
    assert token is not None
    response=_NativeAudioRoomResponse(
        n.room.verified_artifact_path(artifact),
        media_type=artifact.media_type,filename=artifact.filename,
        room=n.room,transport_token=token,artifact_size=artifact.size,
    )
    async def receive():
        return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        return None
    scope={
        'type':'http','method':'GET','path':f'/room/files/{artifact.id}',
        'headers':[],'extensions':{},'http_version':'1.1','scheme':'http',
        'server':('test',80),'client':('test',1),
    }
    asyncio.run(response(scope,receive,send))
    extra={
        'action_delta':{
            k:int(st.action_observations.get(k,0))-int(before_actions.get(k,0))
            for k in set(before_actions)|set(st.action_observations)
        },
        'transition_delta':int(st.transition_observations)-before_trans,
    }
elif op!='inspect':
    raise SystemExit('bad op')

arts=n.store.room_artifacts()
pres=n.store.native_presentations()
audio=n.store.native_audio_transport_receipts()
print(json.dumps({
    'pending_action':st.pending_action,
    'receipt_id':str(st.pending_execution_receipt.receipt_id) if st.pending_execution_receipt else None,
    'receipt_type':type(st.pending_execution_receipt).__name__ if st.pending_execution_receipt else None,
    'artifacts':len(arts),
    'artifact_ids':[str(a.id) for a in arts],
    'artifact_cognitive_authority':[a.cognitive_authority for a in arts],
    'artifact_publication_native_choice_claim':[a.publication_native_choice_claim for a in arts],
    'presentations':len(pres),
    'presentation_ids':[str(p.id) for p in pres],
    'presentation_resolution_confirmed':[p.source_resolution_execution_confirmed for p in pres],
    'presentation_receipt_ids':[
        str(p.source_resolution_receipt_id) if p.source_resolution_receipt_id else None
        for p in pres
    ],
    'audio_receipts':len(audio),
    'audio_playback_confirmed':[r.playback_confirmed for r in audio],
    'action_observations':dict(st.action_observations),
    'transition_observations':st.transition_observations,
    'restart_audit':dict(getattr(n,'_hf2_restart_recovery_audit',{})),
    **extra,
},sort_keys=True))
'''

PHASE_CODES={
    'after-receipt-before-presentation':80,
    'after-voice-before-artifact':81,
    'after-artifact-before-presentation':82,
    'after-presentation-before-followup':83,
}

def run_crash(db:Path,markers:Path,phase:str):
    p=subprocess.run(
        [sys.executable,'-c',CHILD,phase,str(db),str(markers)],
        text=True,capture_output=True,env=os.environ.copy(),
    )
    assert p.returncode==PHASE_CODES[phase],(phase,p.returncode,p.stdout,p.stderr)

def inspect(db:Path,op='inspect'):
    p=subprocess.run(
        [sys.executable,'-c',INSPECT,str(db),op],
        text=True,capture_output=True,env=os.environ.copy(),check=True,
    )
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_crash_after_receipt_before_presentation_preserves_execution_without_replay(tmp_path):
    db=tmp_path/'r.sqlite3';markers=tmp_path/'r-markers'
    run_crash(db,markers,'after-receipt-before-presentation')
    assert (markers/'receipt-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='clarify' and s['receipt_type']=='ResolutionExecutionReceipt'
    assert s['artifacts']==s['presentations']==s['audio_receipts']==0
    s2=inspect(db)
    assert (s2['artifacts'],s2['presentations'],s2['audio_receipts'])==(0,0,0)


def test_crash_after_voice_choice_before_artifact_does_not_fabricate_durable_presentation(tmp_path):
    db=tmp_path/'v.sqlite3';markers=tmp_path/'v-markers'
    run_crash(db,markers,'after-voice-before-artifact')
    assert (markers/'voice-selected').exists()
    s=inspect(db)
    assert s['pending_action']=='clarify'
    assert s['artifacts']==s['presentations']==s['audio_receipts']==0


def test_crash_after_artifact_before_presentation_keeps_orphan_artifact_nonsemantic_and_unpromoted(tmp_path):
    db=tmp_path/'a.sqlite3';markers=tmp_path/'a-markers'
    run_crash(db,markers,'after-artifact-before-presentation')
    assert (markers/'artifact-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='clarify'
    assert s['artifacts']==1 and s['presentations']==0 and s['audio_receipts']==0
    assert s['artifact_cognitive_authority']==[False]
    assert s['artifact_publication_native_choice_claim']==[True]
    s2=inspect(db)
    assert s2['artifacts']==1 and s2['presentations']==0 and s2['audio_receipts']==0


def test_crash_after_presentation_before_fetch_restores_exactly_one_linked_presentation_without_transport(tmp_path):
    db=tmp_path/'p.sqlite3';markers=tmp_path/'p-markers'
    run_crash(db,markers,'after-presentation-before-followup')
    assert (markers/'presentation-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='clarify'
    assert s['artifacts']==1 and s['presentations']==1 and s['audio_receipts']==0
    assert s['presentation_resolution_confirmed']==[True]
    assert s['presentation_receipt_ids']==[s['receipt_id']]
    s2=inspect(db)
    assert s2['artifacts']==1 and s2['presentations']==1 and s2['audio_receipts']==0


@pytest.mark.parametrize('phase',list(PHASE_CODES))
def test_each_restart_boundary_preserves_at_most_once_consequence_learning(phase,tmp_path):
    db=tmp_path/f'{phase}.sqlite3';markers=tmp_path/f'{phase}-markers'
    run_crash(db,markers,phase)
    first=inspect(db,'consume')
    assert first['transition_delta']==1
    assert first['action_delta'].get('clarify')==1
    assert first['pending_action']=='' and first['receipt_id'] is None
    second=inspect(db,'consume')
    assert second['transition_delta']==0
    assert all(v==0 for v in second['action_delta'].values())


def test_durable_presentation_can_be_transported_after_restart_without_speech_act_learning_or_playback_claim(tmp_path):
    db=tmp_path/'fetch.sqlite3';markers=tmp_path/'fetch-markers'
    run_crash(db,markers,'after-presentation-before-followup')
    before=inspect(db)
    assert before['audio_receipts']==0 and before['presentations']==1
    after=inspect(db,'fetch-audio')
    assert after['audio_receipts']==1
    assert after['audio_playback_confirmed']==[False]
    assert after['transition_delta']==0
    assert all(v==0 for v in after['action_delta'].values())
    assert after['pending_action']=='clarify'
