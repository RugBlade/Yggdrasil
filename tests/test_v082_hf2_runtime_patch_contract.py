from pathlib import Path


PATCH = Path("patches/hf2/0002-hf2-current-turn-runtime-bridge.patch")


def _text() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_patch_targets_exact_hf1_runtime_surfaces():
    s = _text()
    assert "--- a/src/noeron/models.py" in s
    assert "--- a/src/noeron/orchestrator.py" in s
    assert "--- a/src/noeron/api.py" in s


def test_reply_carries_reply_local_current_turn_interpretation():
    s = _text()
    assert "language_interpretation: dict[str,Any] = Field(default_factory=dict)" in s
    assert "language_interpretation=current_language_interpretation" in s


def test_message_simple_stops_reading_stale_serialized_last_interpretation():
    s = _text()
    removed = "-'owner_authenticated':ok,'owner_command':r.owner_command,'language_interpretation':(lang.last_interpretation.model_dump(mode='json') if lang.last_interpretation else None)"
    assert "lang.last_interpretation.model_dump" in s  # historical removed line remains visible in diff evidence
    assert "+            'owner_authenticated':ok,'owner_command':r.owner_command,'language_interpretation':dict(out.language_interpretation)," in s


def test_bridge_is_admitted_only_after_security_and_from_current_irg_propositions():
    s = _text()
    assert "propositions=list(result.state.irg.logical_propositions)" in s
    assert "native_trace=native_trace_from_math_state(result.state,event_id=str(event.id))" in s
    assert "prospective_floor_turn=self._hf2_premise_floor_turn" in s


def test_runtime_patch_explicitly_preserves_authority_boundaries():
    s = _text()
    assert "It cannot alter truth," in s
    assert "answer selection, memory, relationship state, or native speech choice" in s
    assert "Historical dialogue is deliberately not replayed as cognitive truth" in s
