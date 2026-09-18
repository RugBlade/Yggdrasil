from __future__ import annotations

import base64
import io
import json
import math
import socket
import struct
import threading
import time
import wave
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from playwright.sync_api import sync_playwright

import noeron.api as api
from noeron.auth import OwnerAuthenticator
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.orchestrator import Noeron
from noeron.room_models import NativePresentationRecord, NativeRoomDecision


def _wav_bytes(seconds: float = 2.5, rate: int = 8_000) -> bytes:
    frames = int(seconds * rate)
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        payload = bytearray()
        for i in range(frames):
            sample = int(0.08 * 32767 * math.sin(2 * math.pi * 440.0 * i / rate))
            payload.extend(struct.pack("<h", sample))
        w.writeframes(bytes(payload))
    return raw.getvalue()


def _seed_native_audio(n: Noeron, store: LocalEventStore):
    decision = NativeRoomDecision(
        domain="native-voice",
        selected_action="voice",
        selection_status="selected-unique-native-minimum",
        decision_layer="native-deliberative",
        native_choice_claim=True,
    )
    data = _wav_bytes()
    artifact = n.room._publish_bytes(
        data,
        "m4c3n-browser.wav",
        "audio/wav",
        decision,
        expected_domain="native-voice",
        expected_action="voice",
    )
    native = "m4c3n-browser-native"
    presentation = NativePresentationRecord(
        source="m4c3n-browser-test",
        native_text_sha256=sha256(native.encode()).hexdigest(),
        native_text_private=native,
        audio_artifact_id=artifact.id,
        audio_sha256=artifact.sha256,
        voice_native_choice_claim=True,
        voice_decision_id=decision.id,
    )
    store.append_native_presentation(presentation)
    return presentation, artifact


def _session(auth: OwnerAuthenticator, device_id: str = "m4c3n-browser-device"):
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    auth.enroll_device(
        device_id,
        "M4C3N isolated browser device",
        base64.b64encode(raw).decode(),
        authority="isolated-browser-test",
    )
    challenge = auth.challenge(device_id)
    signature = base64.b64encode(private.sign(challenge["message"].encode())).decode()
    token = auth.create_device_session(
        device_id, challenge["challenge_id"], signature
    )["session_token"]
    return token, private


def _renew_session(auth: OwnerAuthenticator, device_id: str, private: Ed25519PrivateKey) -> str:
    challenge = auth.challenge(device_id)
    signature = base64.b64encode(private.sign(challenge["message"].encode())).decode()
    return auth.create_device_session(
        device_id, challenge["challenge_id"], signature
    )["session_token"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _serve(app):
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("isolated Room server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _fresh_runtime(tmp_path: Path, monkeypatch):
    store = LocalEventStore(tmp_path / f"m4c3n-{uuid4().hex}.sqlite3")
    n = Noeron(MockLanguageEngine(), store, terra_enabled=False)
    auth = OwnerAuthenticator("", store, legacy_enabled=False)
    monkeypatch.setattr(api, "store", store)
    monkeypatch.setattr(api, "noeron", n)
    monkeypatch.setattr(api, "owner_auth", auth)
    p, a = _seed_native_audio(n, store)
    token, private = _session(auth)
    return n, store, auth, p, a, token, private


def _browser(base: str, token: str):
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--autoplay-policy=no-user-gesture-required", "--disable-gpu"],
    )
    context = browser.new_context()
    context.add_cookies(
        [
            {
                "name": api._ROOM_COOKIE,
                "value": token,
                "url": base + "/room",
                "httpOnly": True,
                "sameSite": "Strict",
            }
        ]
    )
    page = context.new_page()
    page.goto(base + "/room", wait_until="domcontentloaded")
    page.wait_for_selector("audio", state="attached", timeout=10_000)
    return pw, browser, context, page


def _close_browser(parts):
    pw, browser, context, _page = parts
    context.close()
    browser.close()
    pw.stop()


def _wait_receipts(store: LocalEventStore, count: int, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = store.native_audio_client_playback_receipts(100)
        if len(rows) >= count:
            return rows
        time.sleep(0.05)
    return store.native_audio_client_playback_receipts(100)


def _wait_audio_eval(page, expression: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.eval_on_selector("audio", expression):
            return
        time.sleep(0.05)
    raise AssertionError(f"audio predicate did not become true: {expression}")


def _ensure_transport(page, store: LocalEventStore, artifact_id: str):
    before = len(store.native_audio_transport_receipts(100))
    page.evaluate(
        """async () => {
          const a=document.querySelector('audio');
          const r=await fetch(a.src,{credentials:'same-origin',cache:'no-store'});
          await r.arrayBuffer();
        }"""
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        rows = store.native_audio_transport_receipts(100)
        if len(rows) > before and any(str(r.audio_artifact_id) == artifact_id for r in rows):
            return rows[-1]
        time.sleep(0.05)
    raise AssertionError("durable native audio transport receipt did not appear")


def test_real_chromium_keeps_same_audio_element_through_snapshot_transport_and_telemetry(tmp_path, monkeypatch):
    n, store, _auth, p, a, token, _private = _fresh_runtime(tmp_path, monkeypatch)
    with _serve(api.app) as base:
        parts = _browser(base, token)
        page = parts[-1]
        try:
            assert page.eval_on_selector("audio", "a => a.paused") is True
            page.evaluate("window.__m4c3nAudio=document.querySelector('audio')")

            n.room.append_journal("m4c3n-browser-churn", {"cognitive_authority": False})
            page.wait_for_timeout(1000)
            assert page.evaluate("document.querySelector('audio')===window.__m4c3nAudio") is True

            _ensure_transport(page, store, str(a.id))
            page.wait_for_timeout(1000)
            assert page.evaluate("document.querySelector('audio')===window.__m4c3nAudio") is True

            page.eval_on_selector("audio", "a => {a.muted=true; return a.play()}")
            _wait_audio_eval(page, "a => a.dataset.playingReported==='1'")
            rows = _wait_receipts(store, 1)
            assert [r.event for r in rows] == ["playing"]
            sid = rows[0].playback_session_id
            assert page.evaluate("document.querySelector('audio')===window.__m4c3nAudio") is True

            page.eval_on_selector("audio", "a => a.pause()")
            page.wait_for_timeout(200)
            page.eval_on_selector("audio", "a => a.play()")
            page.wait_for_timeout(350)
            assert len(store.native_audio_client_playback_receipts(100)) == 1

            _wait_audio_eval(page, "a => a.ended===true")
            rows = _wait_receipts(store, 2)
            assert [r.event for r in rows] == ["playing", "ended"]
            assert rows[0].playback_session_id == rows[1].playback_session_id == sid
            assert page.evaluate("document.querySelector('audio')===window.__m4c3nAudio") is True
            for r in rows:
                assert r.audible_output_confirmed is False
                assert r.peer_heard_confirmed is False
                assert r.peer_understanding_confirmed is False
                assert r.peer_reply_causation_confirmed is False
                assert r.speech_act_choice_authority is False
                assert r.preference_label_authority is False
                assert r.relationship_authority is False
                assert r.cognitive_memory_authority is False
        finally:
            _close_browser(parts)


def test_real_chromium_network_uncertainty_retries_identical_playback_identity(tmp_path, monkeypatch):
    _n, store, _auth, _p, a, token, _private = _fresh_runtime(tmp_path, monkeypatch)
    with _serve(api.app) as base:
        parts = _browser(base, token)
        page = parts[-1]
        seen = []
        try:
            _ensure_transport(page, store, str(a.id))

            def intercept(route, request):
                payload = json.loads(request.post_data or "{}")
                seen.append(payload)
                if len(seen) == 1:
                    response = route.fetch()
                    assert response.ok
                    route.abort("failed")
                else:
                    route.continue_()

            page.route("**/client-playback", intercept)
            page.eval_on_selector("audio", "a => {a.muted=true; return a.play()}")
            _wait_audio_eval(page, "a => a.dataset.playingReported==='1'")
            page.eval_on_selector("audio", "a => a.pause()")
            assert len(seen) == 2
            assert seen[0] == seen[1]
            assert seen[0]["playback_session_id"] == seen[1]["playback_session_id"]
            rows = store.native_audio_client_playback_receipts(100)
            assert len(rows) == 1 and rows[0].event == "playing"
            assert str(rows[0].playback_session_id) == seen[0]["playback_session_id"]
        finally:
            _close_browser(parts)


@pytest.mark.parametrize("status", [401, 403, 422, 500])
def test_real_chromium_explicit_non409_http_failure_does_not_retry(tmp_path, monkeypatch, status):
    _n, store, _auth, _p, a, token, _private = _fresh_runtime(tmp_path, monkeypatch)
    with _serve(api.app) as base:
        parts = _browser(base, token)
        page = parts[-1]
        seen = []
        try:
            _ensure_transport(page, store, str(a.id))

            def intercept(route, request):
                seen.append(json.loads(request.post_data or "{}"))
                route.fulfill(
                    status=status,
                    content_type="application/json",
                    body=json.dumps({"detail": f"m4c3n-{status}"}),
                )

            page.route("**/client-playback", intercept)
            page.eval_on_selector("audio", "a => {a.muted=true; return a.play()}")
            page.wait_for_timeout(1000)
            page.eval_on_selector("audio", "a => a.pause()")
            assert len(seen) == 1
            assert store.native_audio_client_playback_receipts(100) == []
            assert page.eval_on_selector("audio", "a => !!a.dataset.playbackSessionId") is False
        finally:
            _close_browser(parts)


def test_reload_and_renewed_authenticated_session_cannot_close_old_playback(tmp_path, monkeypatch):
    _n, store, auth, p, a, token_a, private = _fresh_runtime(tmp_path, monkeypatch)
    with _serve(api.app) as base:
        parts_a = _browser(base, token_a)
        page_a = parts_a[-1]
        try:
            _ensure_transport(page_a, store, str(a.id))
            page_a.eval_on_selector("audio", "a => {a.muted=true; return a.play()}")
            _wait_audio_eval(page_a, "a => a.dataset.playingReported==='1'")
            page_a.eval_on_selector("audio", "a => a.pause()")
            playing = _wait_receipts(store, 1)[0]
            sid = str(playing.playback_session_id)

            page_a.reload(wait_until="domcontentloaded")
            page_a.wait_for_selector("audio", state="attached", timeout=10_000)
            page_a.wait_for_timeout(700)
            assert [r.event for r in store.native_audio_client_playback_receipts(100)] == ["playing"]

            token_b = _renew_session(auth, "m4c3n-browser-device", private)
            browser = parts_a[1]
            context_b = browser.new_context()
            context_b.add_cookies(
                [{
                    "name": api._ROOM_COOKIE,
                    "value": token_b,
                    "url": base + "/room",
                    "httpOnly": True,
                    "sameSite": "Strict",
                }]
            )
            page_b = context_b.new_page()
            page_b.goto(base + "/room", wait_until="domcontentloaded")
            page_b.wait_for_selector("audio", state="attached", timeout=10_000)
            try:
                result = page_b.evaluate(
                    """async ({pid,aid,sid}) => {
                      const r=await fetch('/room/native/presentations/'+pid+'/client-playback',{
                        method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},
                        body:JSON.stringify({audio_artifact_id:aid,playback_session_id:sid,event:'ended',
                          current_time_seconds:1,duration_seconds:2.5,muted:true,volume:1,playback_rate:1})});
                      return {status:r.status,body:await r.json()};
                    }""",
                    {"pid": str(p.id), "aid": str(a.id), "sid": sid},
                )
                assert result["status"] == 409
                assert "prior playing" in str(result["body"])
                assert [r.event for r in store.native_audio_client_playback_receipts(100)] == ["playing"]
            finally:
                context_b.close()
        finally:
            _close_browser(parts_a)


def test_room_product_code_contains_no_autoplay_or_programmatic_native_audio_play():
    html = api._ROOM_HTML
    assert "<audio autoplay" not in html
    assert "a.autoplay" not in html
    start = html.index("function configurePresentationAudio")
    end = html.index("function reconcilePresentations", start)
    assert ".play()" not in html[start:end]
