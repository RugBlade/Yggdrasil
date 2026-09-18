from pathlib import Path


INTENT = Path("patches/hf2/0005-hf2-native-resolution-state-audit.intent.patch")


def text():
    return INTENT.read_text(encoding="utf-8")


def test_0005_intent_targets_state_reply_and_orchestrator_only():
    p = text()
    assert "src/noeron/cognition/models.py" in p
    assert "src/noeron/models.py" in p
    assert "src/noeron/orchestrator.py" in p


def test_0005_has_no_fabricated_observations_or_canned_content():
    p = text().lower()
    assert "action_observations: dict[str,int] = field(default_factory=dict)" in p
    assert "last_native_choice_claim: bool = false" in p
    assert "please clarify" not in p
    assert "i don't know" not in p
    assert "i do not know" not in p


def test_0005_uses_actual_postclosure_native_geometry():
    p = text()
    assert "InitiativePolicy._transport_transition" in p
    assert "equal_affordance_post_manifold" in p
    assert "distance_fn=dkt.sobolev_distance" in p
    assert "tied_fn=numerically_tied" in p
    assert "post-closure-DKT-after-IRG-DKT-regional-EGR-RL-Frenet-DKT" in p


def test_0005_does_not_change_transport_yet():
    p = text()
    assert "'changes_outward_transport':False" in p
    assert "'changes_native_content':False" in p
