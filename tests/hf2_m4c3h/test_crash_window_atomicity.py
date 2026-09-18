"""M4C3H true process-crash windows around resolution receipt durability.

All crashes happen in disposable child processes against isolated SQLite databases.
Synthetic consequence geometry is test-only and does not become product preference.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CHILD = r'''
import asyncio,json,os,sys
from pathlib import Path
from noeron.cognition import models as cm
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind
from noeron.orchestrator import Noeron

mode,dbs,phase,marker_dir=sys.argv[1:5]
db=Path(dbs); markers=Path(marker_dir); markers.mkdir(parents=True,exist_ok=True)

def seed_resolution_geometry(n,target):
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

def arm(n,target,expression=False):
    actual=n._resolution_speech_act_selection
    seeded=False
    def wrapped(thought,result,**kwargs):
        nonlocal seeded
        if not seeded:
            seed_resolution_geometry(n,target)
            if expression:seed_expression_geometry(n)
            seeded=True
        return actual(thought,result,**kwargs)
    n._resolution_speech_act_selection=wrapped

def crash_append_wrapper(n,phase):
    real=n.store.append_state
    def wrapped(state):
        receipt=state.cognition.speech_act_development.pending_execution_receipt
        if receipt is None:
            return real(state)
        (markers/'receipt-state-reached').write_text(str(receipt.receipt_id))
        if phase=='pre-append':
            os._exit(71)
        if phase=='post-append':
            real(state)
            (markers/'receipt-state-durable').write_text(str(receipt.receipt_id))
            os._exit(72)
        return real(state)
    n.store.append_state=wrapped

n=Noeron(MockLanguageEngine(),LocalEventStore(db),terra_enabled=False)

if mode=='content':
    n.state.cognition.language.dialogue.recent_referents=[
        cm.DialogueReferent(surface='Mira',kind='person'),cm.DialogueReferent(surface='Sara',kind='person')]
    arm(n,'clarify',expression=True)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3h-origin',content='She moved.',metadata={'owner_authenticated':True})
    reply=n.ingest(event,resolution_channel='authenticated-owner-room-http')
    assert reply._resolution_dispatch is not None
    (markers/'prepared').write_text(str(event.id))
    from noeron.api import _ResolutionRoomResponse
    response=_ResolutionRoomResponse({'text':reply.text},n,reply._resolution_dispatch)
    real=n.store.append_state
    if phase in {'pre-append','post-append'}:
        def wrapped(state):
            receipt=state.cognition.speech_act_development.pending_execution_receipt
            if receipt is None:return real(state)
            (markers/'receipt-state-reached').write_text(str(receipt.receipt_id))
            if phase=='pre-append':os._exit(71)
            real(state);(markers/'receipt-state-durable').write_text(str(receipt.receipt_id));os._exit(72)
        n.store.append_state=wrapped
    async def receive():return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        if message['type']=='http.response.body' and not message.get('more_body',False):
            (markers/'terminal-body-send-entered').write_text('1')
            if phase=='before-send-complete':os._exit(70)
        return None
    asyncio.run(response({'type':'http','method':'POST','path':'/room/message','asgi':{'version':'3.0','spec_version':'2.4'}},receive,send))
    raise SystemExit('content crash mode did not crash')

elif mode in {'defer','remain-silent'}:
    arm(n,mode,expression=False)
    crash_append_wrapper(n,phase)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3h-origin',content='What is a flarble?')
    n.ingest(event)
    raise SystemExit('noncontent crash mode did not crash')
else:
    raise SystemExit('bad mode')
'''

INSPECT = r'''
import json,sys
from datetime import timedelta
from pathlib import Path
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind
from noeron.orchestrator import Noeron

db=Path(sys.argv[1]); op=sys.argv[2]
n=Noeron(MockLanguageEngine(),LocalEventStore(db),terra_enabled=False)
st=n.state.cognition.speech_act_development
ini=n.state.cognition.initiative_development
receipt=st.pending_execution_receipt
before_actions=dict(st.action_observations);before_trans=int(st.transition_observations)
extra={}
if op=='consume':
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3h-later',content='Mira moved book.',created_at=(receipt.completed_at+timedelta(seconds=2) if receipt else None)) if receipt else CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3h-later',content='Mira moved book.')
    n.ingest(event)
    extra={'action_delta':{k:int(st.action_observations.get(k,0))-int(before_actions.get(k,0)) for k in set(before_actions)|set(st.action_observations)},'transition_delta':int(st.transition_observations)-before_trans}
elif op=='duplicate-noncontent':
    original=n.store.event_by_id(str(st.pending_event_id)) if st.pending_event_id else None
    extra['duplicate']=n._commit_noncontent_resolution_execution(original) if original else None
elif op!='inspect':raise SystemExit('bad op')
receipt=st.pending_execution_receipt
print(json.dumps({
 'pending_action':st.pending_action,
 'receipt_type':type(receipt).__name__ if receipt else None,
 'receipt_id':str(receipt.receipt_id) if receipt else None,
 'pending_origin':st.pending_origin,
 'expression_receipt_id':str(ini.pending_expression_receipt_id) if ini.pending_expression_receipt_id else None,
 'dispatch_present':n._hf2_resolution_dispatch is not None,
 'receipt_capability_present':n._hf2_receipt_to_mark is not None,
 'action_observations':dict(st.action_observations),
 'transition_observations':st.transition_observations,
 'last_outcome_audit':dict(st.last_outcome_audit or {}),
 'restart_audit':dict(getattr(n,'_hf2_restart_recovery_audit',{})),
 **extra,
},sort_keys=True))
'''


def run_crash(db:Path,markers:Path,mode:str,phase:str):
    p=subprocess.run([sys.executable,'-c',CHILD,mode,str(db),phase,str(markers)],text=True,capture_output=True,env=os.environ.copy())
    assert p.returncode in {70,71,72}, (p.returncode,p.stdout,p.stderr)
    return p.returncode


def inspect(db:Path,op='inspect'):
    p=subprocess.run([sys.executable,'-c',INSPECT,str(db),op],text=True,capture_output=True,env=os.environ.copy(),check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_content_crash_before_send_completion_has_no_receipt_or_replay(tmp_path):
    db=tmp_path/'content-before.sqlite3';markers=tmp_path/'m1'
    assert run_crash(db,markers,'content','before-send-complete')==70
    assert (markers/'terminal-body-send-entered').exists()
    s=inspect(db)
    assert s['pending_action']=='' and s['receipt_id'] is None
    assert s['dispatch_present'] is s['receipt_capability_present'] is False
    after=inspect(db,'consume')
    assert after['transition_delta']==0
    assert all(v==0 for v in after['action_delta'].values())


def test_content_send_completed_but_crash_before_receipt_append_is_nonlearnable_and_not_replayed(tmp_path):
    db=tmp_path/'content-preappend.sqlite3';markers=tmp_path/'m2'
    assert run_crash(db,markers,'content','pre-append')==71
    assert (markers/'terminal-body-send-entered').exists()
    assert (markers/'receipt-state-reached').exists()
    assert not (markers/'receipt-state-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='' and s['receipt_id'] is None
    assert s['dispatch_present'] is s['receipt_capability_present'] is False
    after=inspect(db,'consume')
    assert after['transition_delta']==0
    assert all(v==0 for v in after['action_delta'].values())


def test_content_crash_after_receipt_append_recovers_pending_and_consumes_once(tmp_path):
    db=tmp_path/'content-postappend.sqlite3';markers=tmp_path/'m3'
    assert run_crash(db,markers,'content','post-append')==72
    assert (markers/'terminal-body-send-entered').exists()
    assert (markers/'receipt-state-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='clarify' and s['receipt_type']=='ResolutionExecutionReceipt'
    assert s['expression_receipt_id']==s['receipt_id']
    assert s['dispatch_present'] is False
    first=inspect(db,'consume')
    assert first['transition_delta']==1
    assert first['action_delta'].get('clarify')==1
    assert first['pending_action']=='' and first['receipt_id'] is None
    second=inspect(db,'consume')
    assert second['transition_delta']==0
    assert all(v==0 for v in second['action_delta'].values())


@pytest.mark.parametrize('action',['defer','remain-silent'])
def test_noncontent_crash_before_receipt_append_has_no_durable_execution(action,tmp_path):
    db=tmp_path/f'{action}-pre.sqlite3';markers=tmp_path/f'{action}-pre'
    assert run_crash(db,markers,action,'pre-append')==71
    assert (markers/'receipt-state-reached').exists()
    assert not (markers/'receipt-state-durable').exists()
    s=inspect(db)
    assert s['pending_action']=='' and s['receipt_id'] is None
    after=inspect(db,'consume')
    assert after['transition_delta']==0
    assert all(v==0 for v in after['action_delta'].values())


@pytest.mark.parametrize('action',['defer','remain-silent'])
def test_noncontent_crash_after_receipt_append_recovers_blocks_duplicate_and_consumes_once(action,tmp_path):
    db=tmp_path/f'{action}-post.sqlite3';markers=tmp_path/f'{action}-post'
    assert run_crash(db,markers,action,'post-append')==72
    assert (markers/'receipt-state-durable').exists()
    s=inspect(db)
    assert s['pending_action']==action and s['receipt_type']=='NonContentResolutionExecutionReceipt'
    assert s['expression_receipt_id'] is None
    dup=inspect(db,'duplicate-noncontent')
    assert dup['duplicate']['executed'] is False
    assert dup['duplicate']['status']=='pending-or-dispatch-conflict'
    first=inspect(db,'consume')
    assert first['transition_delta']==1
    assert first['action_delta'].get(action)==1
    second=inspect(db,'consume')
    assert second['transition_delta']==0
    assert all(v==0 for v in second['action_delta'].values())
