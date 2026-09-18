"""M4C3G: true same-SQLite restart/recovery for receipted resolution execution.

The receipt-producing fixtures use the real post-0013 trusted execution paths.  Each
restart assertion constructs a brand-new Python process and Noeron instance against
the same isolated SQLite file.  Synthetic consequence geometry is test-only; it never
becomes a product default or authored preference.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from noeron.cognition import models as cm
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind, NoeronState
from noeron.orchestrator import Noeron

CHANNEL = "authenticated-owner-room-http"
ACTS = ("clarify", "ask", "defer", "remain-silent")


def seed_resolution_geometry(n: Noeron, target: str) -> None:
    context = n.state.math_kernel.dkt.core_knot
    st = n.state.cognition.speech_act_development
    for i, action in enumerate(ACTS, 1):
        pre = context.model_copy(deep=True)
        if action != target:
            pre.c0[0] += i * 0.2
        pre.invariant_signature = dkt.invariant_signature(pre)
        st.action_pre_knots[action] = pre
        st.action_post_knots[action] = context.model_copy(deep=True)
        st.action_observations[action] = 1
    st.transition_observations = 4


def seed_expression_geometry(n: Noeron) -> None:
    context = n.state.math_kernel.dkt.core_knot
    st = n.state.cognition.initiative_development
    for action in ("express", "continue-private"):
        pre = context.model_copy(deep=True)
        if action != "express":
            pre.c0[1] += 0.5
        pre.invariant_signature = dkt.invariant_signature(pre)
        st.action_pre_knots[action] = pre
        st.action_post_knots[action] = context.model_copy(deep=True)
        st.action_observations[action] = 1
    st.admissible_post_knot = context.model_copy(deep=True)
    st.admissible_post_observations = 2
    st.transition_observations = 2


def arm_native_resolution(n: Noeron, target: str, *, expression: bool = False) -> None:
    actual = n._resolution_speech_act_selection
    seeded = False

    def wrapped(thought, result, **kwargs):
        nonlocal seeded
        if not seeded:
            seed_resolution_geometry(n, target)
            if expression:
                seed_expression_geometry(n)
            seeded = True
        return actual(thought, result, **kwargs)

    n._resolution_speech_act_selection = wrapped


def make_noncontent_receipt(db: Path, action: str = "defer"):
    n = Noeron(MockLanguageEngine(), LocalEventStore(db), terra_enabled=False)
    arm_native_resolution(n, action)
    event = CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="m4c3g-origin",
        content="What is a flarble?",
    )
    reply = n.ingest(event)
    st = n.state.cognition.speech_act_development
    receipt = st.pending_execution_receipt
    assert reply.text == ""
    assert reply.speech_act_audit["action"] == action
    assert reply.speech_act_audit["execution_status"] == "local-noncontent-action-committed"
    assert isinstance(receipt, cm.NonContentResolutionExecutionReceipt)
    assert receipt.action == st.pending_action == action
    assert n.store.event_by_id(str(event.id)) is not None
    return n, event, receipt


def make_content_receipt(db: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(db), terra_enabled=False)
    n.state.cognition.language.dialogue.recent_referents = [
        cm.DialogueReferent(surface="Mira", kind="person"),
        cm.DialogueReferent(surface="Sara", kind="person"),
    ]
    arm_native_resolution(n, "clarify", expression=True)
    event = CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="m4c3g-origin",
        content="She moved.",
        metadata={"owner_authenticated": True},
    )
    reply = n.ingest(event, resolution_channel=CHANNEL)
    assert reply._resolution_dispatch is not None
    assert reply.speech_act_audit["action"] == "clarify"
    assert reply.speech_act_audit["execution_status"] == "prepared-awaiting-asgi-send"

    from noeron.api import _ResolutionRoomResponse

    response = _ResolutionRoomResponse({"text": reply.text}, n, reply._resolution_dispatch)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(
        response(
            {"type": "http", "method": "POST", "path": "/room/message", "asgi": {"version": "3.0", "spec_version": "2.4"}},
            receive,
            send,
        )
    )
    st = n.state.cognition.speech_act_development
    receipt = st.pending_execution_receipt
    assert isinstance(receipt, cm.ResolutionExecutionReceipt)
    assert receipt.action == st.pending_action == "clarify"
    assert n.state.cognition.initiative_development.pending_expression_receipt_id == receipt.receipt_id
    assert n.store.event_by_id(str(event.id)) is not None
    return n, event, receipt


CHILD = r"""
import json,sys
from datetime import timedelta
from pathlib import Path
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent,EventKind
from noeron.orchestrator import Noeron

db=Path(sys.argv[1]); mode=sys.argv[2]
n=Noeron(MockLanguageEngine(),LocalEventStore(db),terra_enabled=False)
st=n.state.cognition.speech_act_development
ini=n.state.cognition.initiative_development
receipt=st.pending_execution_receipt

def snapshot(extra=None):
    r=st.pending_execution_receipt
    data={
        'pending_action':st.pending_action,
        'receipt_type':type(r).__name__ if r is not None else None,
        'receipt_id':str(r.receipt_id) if r is not None else None,
        'pending_origin':st.pending_origin,
        'pending_pre_knot':st.pending_pre_knot is not None,
        'pending_pre_residual':st.pending_pre_residual,
        'last_execution_receipt_id':str(st.last_execution_receipt.receipt_id) if st.last_execution_receipt is not None else None,
        'expression_pre_knot':ini.pending_expression_pre_knot is not None,
        'expression_receipt_id':str(ini.pending_expression_receipt_id) if ini.pending_expression_receipt_id else None,
        'dispatch_present':n._hf2_resolution_dispatch is not None,
        'mark_capability_present':n._hf2_receipt_to_mark is not None,
        'action_observations':dict(st.action_observations),
        'transition_observations':st.transition_observations,
        'restart_audit':dict(getattr(n,'_hf2_restart_recovery_audit',{})),
        'last_outcome_audit':dict(st.last_outcome_audit or {}),
        'knot_memory_count':len(n.store.all_knot_memories()),
    }
    if extra:data.update(extra)
    print(json.dumps(data,sort_keys=True))

if mode=='inspect':
    snapshot()
elif mode=='consume':
    if receipt is None:raise SystemExit('missing pending receipt')
    before=dict(st.action_observations);before_t=int(st.transition_observations)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3g-later',content='Mira moved book.',created_at=receipt.completed_at+timedelta(seconds=2))
    n.ingest(event)
    snapshot({'delta':int(st.action_observations.get(receipt.action,0))-int(before.get(receipt.action,0)),
              'transition_delta':int(st.transition_observations)-before_t})
elif mode=='consume-again':
    before=dict(st.action_observations);before_t=int(st.transition_observations)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='m4c3g-later-again',content='Mira moved book.')
    n.ingest(event)
    snapshot({'all_action_observations_unchanged':dict(st.action_observations)==before,
              'transition_delta':int(st.transition_observations)-before_t})
elif mode=='duplicate-noncontent':
    original=n.store.event_by_id(str(st.pending_event_id))
    before=n.state.model_dump(mode='json')
    out=n._commit_noncontent_resolution_execution(original)
    snapshot({'duplicate_result':out,'state_unchanged':n.state.model_dump(mode='json')==before})
else:
    raise SystemExit('unknown mode')
"""


def child(db: Path, mode: str, *, check: bool = True):
    env = os.environ.copy()
    p = subprocess.run(
        [sys.executable, "-c", CHILD, str(db), mode],
        text=True,
        capture_output=True,
        env=env,
        check=check,
    )
    if not check:
        return p
    return json.loads(p.stdout.strip().splitlines()[-1])


def state_row_count(db: Path) -> int:
    with sqlite3.connect(db) as c:
        return int(c.execute("SELECT COUNT(*) FROM states").fetchone()[0])


@pytest.mark.parametrize("family", ["content", "noncontent"])
def test_true_new_process_reconstructs_receipt_and_linked_prestate_without_execution(family, tmp_path):
    db = tmp_path / f"{family}.sqlite3"
    if family == "content":
        n, _event, receipt = make_content_receipt(db)
        expected_expression = str(receipt.receipt_id)
    else:
        n, _event, receipt = make_noncontent_receipt(db, "defer")
        expected_expression = None
    memories = len(n.store.all_knot_memories())
    snap = child(db, "inspect")
    assert snap["receipt_id"] == str(receipt.receipt_id)
    assert snap["pending_action"] == receipt.action
    assert snap["pending_pre_knot"] is True
    assert snap["pending_pre_residual"] == receipt.pre_residual
    assert snap["last_execution_receipt_id"] == str(receipt.receipt_id)
    assert snap["expression_receipt_id"] == expected_expression
    assert snap["dispatch_present"] is snap["mark_capability_present"] is False
    assert snap["knot_memory_count"] == memories
    assert snap["restart_audit"]["status"] == "valid-persisted-resolution-pending-state-restored"
    assert snap["restart_audit"]["learned"] is False
    assert all(v is False for v in snap["restart_audit"]["authority"].values())


@pytest.mark.parametrize("action", ["defer", "remain-silent"])
def test_true_restart_cannot_repeat_local_noncontent_execution(action, tmp_path):
    db = tmp_path / f"{action}.sqlite3"
    _n, _event, receipt = make_noncontent_receipt(db, action)
    snap = child(db, "duplicate-noncontent")
    assert snap["receipt_id"] == str(receipt.receipt_id)
    assert snap["duplicate_result"]["executed"] is False
    assert snap["duplicate_result"]["status"] == "pending-or-dispatch-conflict"
    assert snap["state_unchanged"] is True


@pytest.mark.parametrize("family", ["content", "noncontent"])
def test_later_admissible_user_message_consumes_persisted_receipt_at_most_once(family, tmp_path):
    db = tmp_path / f"consume-{family}.sqlite3"
    if family == "content":
        _n, _event, receipt = make_content_receipt(db)
    else:
        _n, _event, receipt = make_noncontent_receipt(db, "defer")
    first = child(db, "consume")
    assert first["pending_action"] == "" and first["receipt_id"] is None
    assert first["delta"] == 1 and first["transition_delta"] == 1
    assert first["last_outcome_audit"]["learned"] is True
    assert first["last_outcome_audit"]["execution_receipt"]["receipt_id"] == str(receipt.receipt_id)

    second = child(db, "consume-again")
    assert second["pending_action"] == "" and second["receipt_id"] is None
    assert second["all_action_observations_unchanged"] is True
    assert second["transition_delta"] == 0


@pytest.mark.parametrize("family", ["content", "noncontent"])
def test_replayed_already_consumed_pending_state_recovers_without_second_observation(family, tmp_path):
    db = tmp_path / f"replay-{family}.sqlite3"
    if family == "content":
        n, _event, receipt = make_content_receipt(db)
    else:
        n, _event, receipt = make_noncontent_receipt(db, "defer")
    pending = n.state.model_copy(deep=True)
    consumed = child(db, "consume")
    assert consumed["delta"] == 1

    # Simulate a stale/replayed checkpoint becoming the newest SQLite state.
    LocalEventStore(db).append_state(pending)
    recovered = child(db, "inspect")
    assert recovered["pending_action"] == "" and recovered["receipt_id"] is None
    assert recovered["action_observations"][receipt.action] == 2
    assert recovered["restart_audit"]["status"] == "replayed-consumed-resolution-receipt-recovered-to-latest-prior-valid-state"
    assert recovered["restart_audit"]["receipt_id"] == str(receipt.receipt_id)
    assert recovered["restart_audit"]["learned"] is False
    assert all(v is False for v in recovered["restart_audit"]["authority"].values())

    again = child(db, "consume-again")
    assert again["action_observations"][receipt.action] == 2
    assert again["transition_delta"] == 0


@pytest.mark.parametrize("case", ["action-mismatch", "pre-knot-mismatch", "expression-link-mismatch"])
def test_parseable_mismatched_pending_state_is_cleared_nonlearnable_on_restart(case, tmp_path):
    db = tmp_path / f"mismatch-{case}.sqlite3"
    if case == "expression-link-mismatch":
        n, _event, receipt = make_content_receipt(db)
        n.state.cognition.initiative_development.pending_expression_receipt_id = uuid4()
    else:
        n, _event, receipt = make_noncontent_receipt(db, "defer")
        st = n.state.cognition.speech_act_development
        if case == "action-mismatch":
            st.pending_action = "remain-silent"
        else:
            st.pending_pre_knot.c0[0] += 0.125
    n.store.append_state(n.state)

    snap = child(db, "inspect")
    assert snap["pending_action"] == "" and snap["receipt_id"] is None
    assert snap["expression_receipt_id"] is None and snap["expression_pre_knot"] is False
    assert snap["restart_audit"]["status"] == "invalid-persisted-resolution-pending-state-cleared-nonlearnable"
    assert snap["restart_audit"]["learned"] is False
    assert snap["last_outcome_audit"]["learned"] is False
    assert snap["last_outcome_audit"]["status"] == "restart-rejected-nonlearnable-persisted-resolution-state"
    assert all(v is False for k, v in snap["last_outcome_audit"].items() if k.endswith("_authority"))


@pytest.mark.parametrize("field,value", [("effect", "not-a-valid-effect"), ("action", "not-a-valid-action")])
def test_unparseable_latest_receipt_state_fails_closed_instead_of_booting_fresh(field, value, tmp_path):
    db = tmp_path / f"malformed-{field}.sqlite3"
    _n, _event, _receipt = make_noncontent_receipt(db, "defer")
    before_rows = state_row_count(db)
    with sqlite3.connect(db) as c:
        seq, payload = c.execute("SELECT sequence,payload FROM states ORDER BY sequence DESC LIMIT 1").fetchone()
        raw = json.loads(payload)
        raw["cognition"]["speech_act_development"]["pending_execution_receipt"][field] = value
        c.execute("UPDATE states SET payload=? WHERE sequence=?", (json.dumps(raw, separators=(",", ":")), seq))
        c.commit()

    code = """
from pathlib import Path
import sys
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
Noeron(MockLanguageEngine(),LocalEventStore(Path(sys.argv[1])),terra_enabled=False)
"""
    p = subprocess.run([sys.executable, "-c", code, str(db)], text=True, capture_output=True, env=os.environ.copy())
    assert p.returncode != 0
    assert "PersistedStateValidationError" in p.stderr
    assert "refusing fresh-state fallback" in p.stderr
    assert state_row_count(db) == before_rows


def test_restart_recovery_does_not_create_cognitive_or_relationship_authority(tmp_path):
    db = tmp_path / "authority.sqlite3"
    n, _event, receipt = make_noncontent_receipt(db, "defer")
    before_owner = n.state.cognition.owner_relation.model_dump(mode="json")
    before_memories = len(n.store.all_knot_memories())
    snap = child(db, "inspect")
    assert snap["receipt_id"] == str(receipt.receipt_id)
    assert snap["knot_memory_count"] == before_memories
    assert all(v is False for v in snap["restart_audit"]["authority"].values())
    restored = Noeron(MockLanguageEngine(), LocalEventStore(db), terra_enabled=False)
    assert restored.state.cognition.owner_relation.model_dump(mode="json") == before_owner
