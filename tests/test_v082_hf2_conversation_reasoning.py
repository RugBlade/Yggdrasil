from noeron.conversation_premises import ConversationalPremiseEnvelope, NativeGeometryTrace
from noeron.conversation_reasoning import select_bounded_premises_by_native_geometry


def row(turn, canonical, *, knot=None, status="active", admitted=True):
    subject, relation, obj = canonical.split("::", 2)
    return ConversationalPremiseEnvelope(
        canonical=canonical,
        subject=subject,
        relation=relation,
        object=obj,
        polarity=True,
        source_turn=turn,
        origin="bounded-dialogue-turn",
        admitted=admitted,
        status=status,
        native_trace=NativeGeometryTrace(dkt_support_knot=(knot or {})),
    )


def distance(a, b):
    return abs(float(a["x"]) - float(b["x"]))


def tied(a, b):
    return abs(a - b) <= 1e-12


def test_nearest_source_turns_are_selected_by_injected_geometry_only():
    rows = [
        row(1, "a::is::one", knot={"x": 8.0}),
        row(2, "b::is::two", knot={"x": 2.0}),
        row(3, "c::is::three", knot={"x": 4.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
        limit=2,
    )
    assert [p.source_turn for p in out.selected] == [2, 3]
    assert out.audit["selected_source_turns"] == [2, 3]
    assert out.audit["source_turn_distances"] == {"1": 8.0, "2": 2.0, "3": 4.0}
    assert out.audit["metric_authority"] == "runtime-injected-native-DKT-Hs-distance-only"


def test_exact_cutoff_tie_is_preserved_instead_of_forced_to_one_winner():
    rows = [
        row(1, "a::is::one", knot={"x": 1.0}),
        row(2, "b::is::two", knot={"x": -1.0}),
        row(3, "c::is::three", knot={"x": 5.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
        limit=1,
    )
    assert set(out.audit["selected_source_turns"]) == {1, 2}
    assert {p.source_turn for p in out.selected} == {1, 2}
    assert out.audit["exact_tie_at_cutoff"] is True
    assert out.audit["selection_status"].endswith("cutoff-tie-preserved")


def test_all_active_conflicting_alternatives_from_selected_source_turn_survive():
    rows = [
        row(4, "box::color::red", knot={"x": 1.0}, status="conflict"),
        row(4, "box::color::blue", knot={"x": 1.0}, status="conflict"),
        row(2, "lamp::state::on", knot={"x": 9.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
        limit=1,
    )
    assert {p.object for p in out.selected} == {"red", "blue"}
    assert {p.status for p in out.selected} == {"conflict"}
    assert out.audit["answer_authority"] is False


def test_superseded_expired_and_unadmitted_rows_do_not_enter_selection():
    rows = [
        row(1, "a::is::old", knot={"x": 0.1}, status="superseded"),
        row(2, "b::is::expired", knot={"x": 0.2}, status="expired"),
        row(3, "c::is::hidden", knot={"x": 0.3}, admitted=False),
        row(4, "d::is::active", knot={"x": 4.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
        limit=6,
    )
    assert [p.source_turn for p in out.selected] == [4]


def test_missing_source_geometry_is_audited_and_not_fabricated():
    rows = [
        row(1, "a::is::one", knot=None),
        row(2, "b::is::two", knot={"x": 2.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
        limit=6,
    )
    assert [p.source_turn for p in out.selected] == [2]
    assert out.audit["missing_geometry_source_turns"] == [1]


def test_missing_current_geometry_yields_unresolved_without_calling_metric():
    called = []

    def should_not_run(a, b):
        called.append((a, b))
        raise AssertionError("metric should not run")

    out = select_bounded_premises_by_native_geometry(
        [row(1, "a::is::one", knot={"x": 1.0})],
        current_post_closure_knot={},
        distance_fn=should_not_run,
        tied_fn=tied,
    )
    assert out.selected == ()
    assert called == []
    assert out.audit["selection_status"] == "unresolved-missing-current-dkt-geometry"


def test_invalid_metric_result_is_rejected_not_used_as_ranking_signal():
    def metric(a, b):
        return float("nan") if b["x"] == 1.0 else abs(a["x"] - b["x"])

    rows = [
        row(1, "a::is::one", knot={"x": 1.0}),
        row(2, "b::is::two", knot={"x": 2.0}),
    ]
    out = select_bounded_premises_by_native_geometry(
        rows,
        current_post_closure_knot={"x": 0.0},
        distance_fn=metric,
        tied_fn=tied,
    )
    assert [p.source_turn for p in out.selected] == [2]
    assert out.audit["invalid_distance_source_turns"] == [1]


def test_selection_never_acquires_truth_memory_speech_or_answer_authority():
    out = select_bounded_premises_by_native_geometry(
        [row(1, "a::is::one", knot={"x": 1.0})],
        current_post_closure_knot={"x": 0.0},
        distance_fn=distance,
        tied_fn=tied,
    )
    assert out.audit["semantic_truth_authority"] is False
    assert out.audit["cognitive_memory_authority"] is False
    assert out.audit["speech_act_authority"] is False
    assert out.audit["answer_authority"] is False
    assert out.audit["ordering_authority"] is False


def test_limit_must_be_positive():
    try:
        select_bounded_premises_by_native_geometry(
            [],
            current_post_closure_knot={"x": 0.0},
            distance_fn=distance,
            tied_fn=tied,
            limit=0,
        )
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
