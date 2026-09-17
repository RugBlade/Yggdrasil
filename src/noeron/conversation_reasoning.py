"""HF2 native-geometry activation of bounded conversational premises.

This layer does not interpret sentence meaning and does not choose an answer. It
selects which already-admitted bounded working premises are *eligible to enter*
transparent proof closure by comparing their source-turn post-closure DKT support
geometry with the current post-closure DKT state.

The actual H^s metric is injected by the runtime from ``noeron.math.dkt``. This
carrier module therefore contains no imitation metric and no lexical/content
ranking. Exact metric ties at the selection boundary remain selected together.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from noeron.conversation_premises import ConversationalPremiseEnvelope

DistanceFn = Callable[[Mapping[str, object], Mapping[str, object]], float]
TieFn = Callable[[float, float], bool]


@dataclass(frozen=True)
class BoundedGeometrySelection:
    selected: tuple[ConversationalPremiseEnvelope, ...]
    audit: dict[str, object]


def _support_knot(row: ConversationalPremiseEnvelope) -> Mapping[str, object] | None:
    knot = row.native_trace.dkt_support_knot
    return knot if isinstance(knot, Mapping) and bool(knot) else None


def select_bounded_premises_by_native_geometry(
    envelopes: Iterable[ConversationalPremiseEnvelope],
    *,
    current_post_closure_knot: Mapping[str, object],
    distance_fn: DistanceFn,
    tied_fn: TieFn,
    limit: int = 6,
) -> BoundedGeometrySelection:
    """Select bounded source turns using the runtime's real DKT distance.

    Selection is source-turn geometric activation, not truth assignment. All
    active/conflicting premises from a selected source turn are retained. Expired,
    superseded, unadmitted, non-dialogue-origin, and geometry-less rows cannot enter
    proof closure.

    ``limit`` is the nominal number of source-turn geometry groups, not premise
    rows. If the cutoff source turn is exactly tied with further turns according to
    ``tied_fn``, all tied source turns are retained; no arbitrary semantic winner
    is manufactured.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not current_post_closure_knot:
        return BoundedGeometrySelection(
            selected=(),
            audit={
                "selection_status": "unresolved-missing-current-dkt-geometry",
                "selected_source_turns": [],
                "source_turn_distances": {},
                "missing_geometry_source_turns": [],
                "inconsistent_geometry_source_turns": [],
                "non_dialogue_origin_source_turns": [],
                "invalid_distance_source_turns": [],
                "cutoff_distance": None,
                "exact_tie_at_cutoff": False,
                "semantic_truth_authority": False,
                "answer_authority": False,
                "speech_act_authority": False,
                "cognitive_memory_authority": False,
                "metric_authority": "runtime-injected-native-DKT-Hs-distance-only",
            },
        )

    eligible: list[ConversationalPremiseEnvelope] = []
    missing_turns: set[int] = set()
    inconsistent_turns: set[int] = set()
    non_dialogue_turns: set[int] = set()
    groups: dict[int, tuple[Mapping[str, object], list[ConversationalPremiseEnvelope]]] = {}

    for row in envelopes:
        if not row.admitted or row.status not in {"active", "conflict"}:
            continue
        row.authority.assert_bounded_safe()
        turn = int(row.source_turn)
        if row.origin not in {"current-turn", "bounded-dialogue-turn"}:
            non_dialogue_turns.add(turn)
            continue
        if turn in inconsistent_turns:
            continue
        eligible.append(row)
        knot = _support_knot(row)
        if knot is None:
            missing_turns.add(turn)
            continue
        if turn not in groups:
            groups[turn] = (knot, [row])
        else:
            support, rows = groups[turn]
            # Premises admitted from one turn must refer to the same source-turn
            # geometry. Mismatch invalidates that entire turn rather than selecting
            # one serialization by arrival order.
            if dict(support) != dict(knot):
                inconsistent_turns.add(turn)
                groups.pop(turn, None)
                continue
            rows.append(row)

    distances: dict[int, float] = {}
    invalid_distance_turns: set[int] = set()
    for turn, (support, _rows) in groups.items():
        try:
            d = float(distance_fn(current_post_closure_knot, support))
        except Exception:
            invalid_distance_turns.add(turn)
            continue
        if d < 0.0 or d != d or d in {float("inf"), float("-inf")}:
            invalid_distance_turns.add(turn)
            continue
        distances[turn] = d

    ranked = sorted(distances.items(), key=lambda item: (item[1], item[0]))
    common_audit = {
        "missing_geometry_source_turns": sorted(missing_turns),
        "inconsistent_geometry_source_turns": sorted(inconsistent_turns),
        "non_dialogue_origin_source_turns": sorted(non_dialogue_turns),
        "invalid_distance_source_turns": sorted(invalid_distance_turns),
        "semantic_truth_authority": False,
        "answer_authority": False,
        "speech_act_authority": False,
        "cognitive_memory_authority": False,
        "metric_authority": "runtime-injected-native-DKT-Hs-distance-only",
    }
    if not ranked:
        return BoundedGeometrySelection(
            selected=(),
            audit={
                "selection_status": "unresolved-no-usable-bounded-geometry",
                "selected_source_turns": [],
                "source_turn_distances": {},
                "cutoff_distance": None,
                "exact_tie_at_cutoff": False,
                **common_audit,
            },
        )

    base_count = min(limit, len(ranked))
    cutoff = ranked[base_count - 1][1]
    selected_turns = [turn for turn, _d in ranked[:base_count]]
    tied_beyond_cutoff: list[int] = []
    for turn, d in ranked[base_count:]:
        if tied_fn(d, cutoff):
            selected_turns.append(turn)
            tied_beyond_cutoff.append(turn)
        else:
            break

    selected_set = set(selected_turns)
    selected_rows = tuple(
        row
        for row in eligible
        if int(row.source_turn) in selected_set and int(row.source_turn) in distances
    )
    status = "native-DKT-bounded-premises-selected"
    if tied_beyond_cutoff:
        status = "native-DKT-bounded-premises-selected-with-cutoff-tie-preserved"

    return BoundedGeometrySelection(
        selected=selected_rows,
        audit={
            "selection_status": status,
            "selected_source_turns": selected_turns,
            "source_turn_distances": {str(k): distances[k] for k in sorted(distances)},
            "cutoff_distance": cutoff,
            "exact_tie_at_cutoff": bool(tied_beyond_cutoff),
            "tied_source_turns_beyond_nominal_limit": tied_beyond_cutoff,
            "selected_premise_count": len(selected_rows),
            "ordering_authority": False,
            **common_audit,
        },
    )
