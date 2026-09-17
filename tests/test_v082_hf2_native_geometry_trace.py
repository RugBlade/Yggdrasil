from types import SimpleNamespace

from noeron.conversation_bridge import native_trace_from_math_state
from noeron.conversation_premises import NativeGeometryTrace


def _knot(signature="sig-1"):
    return SimpleNamespace(
        sobolev_order=2.0,
        mode_radius=2,
        c0=[0.0, 0.0, 0.0],
        cosine=[[1.0, 0.0, 0.0], [0.0, 0.5, 0.0]],
        sine=[[0.0, 1.0, 0.0], [0.0, 0.0, 0.5]],
        stratum_index=0,
        invariant_signature=signature,
    )


def test_trace_carries_finite_post_closure_dkt_chart_for_later_hs_comparison():
    math_state = SimpleNamespace(
        dkt=SimpleNamespace(
            retrieved_memory_ids=["mem-1"],
            invariant_signature="sig-1",
            core_knot=_knot(),
        ),
        egr=SimpleNamespace(simultaneous_active_regions=["region:a"], dominant_activation_region="region:a"),
        reasoning=SimpleNamespace(inference_steps=[]),
        frenet=SimpleNamespace(samples=0),
    )
    trace = native_trace_from_math_state(math_state, event_id="evt-1")
    assert trace.dkt_support_knot["sobolev_order"] == 2.0
    assert trace.dkt_support_knot["mode_radius"] == 2
    assert trace.dkt_support_knot["invariant_signature"] == "sig-1"
    assert trace.dkt_support_knot["cosine"][1] == [0.0, 0.5, 0.0]
    assert trace.has_native_trace is True


def test_support_knot_serialization_has_no_authority_fields():
    trace = NativeGeometryTrace(dkt_support_knot={"invariant_signature": "sig"})
    assert "semantic_truth" not in trace.dkt_support_knot
    assert "answer" not in trace.dkt_support_knot
    assert "cognitive_memory" not in trace.dkt_support_knot


def test_missing_post_closure_knot_stays_missing_instead_of_fabricating_geometry():
    math_state = {
        "dkt": {"retrieved_memory_ids": [], "invariant_signature": "sig-only", "core_knot": None},
        "egr": {"simultaneous_active_regions": []},
        "reasoning": {"inference_steps": []},
        "frenet": {"samples": 0},
    }
    trace = native_trace_from_math_state(math_state)
    assert trace.dkt_support_knot == {}
    assert trace.dkt_activation_ids == ("dkt-knot:sig-only",)
