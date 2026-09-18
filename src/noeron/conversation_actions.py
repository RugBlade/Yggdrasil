from __future__ import annotations

"""HF2 Milestone 4A: native unresolved-response speech-act consequence selection.

This carrier defines affordances and a consequence selector; it does not author
utterance text, assign semantic truth, or map a parser label directly to a claimed
Yggdrasil choice.

The runtime integration must inject the already-computed post-closure native
geometry (Environment -> IRG -> DKT -> regional EGR -> RL/Frenet -> DKT) and the
actual DKT transport/distance/tie machinery. Programmed eligibility only says
which actuators are meaningful in the present unresolved-response situation.
A native-choice claim is permitted only when at least two eligible affordances all
have observed admissible consequence geometry and one predicted post-state has a
unique native-geometry minimum. Missing evidence and exact ties remain unresolved.
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence


RESOLUTION_AFFORDANCES = (
    "clarify",
    "ask",
    "defer",
    "remain-silent",
)


@dataclass(frozen=True)
class SpeechActEligibility:
    requires_resolution: bool
    eligible_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    authority: Mapping[str, bool]


def resolution_affordances(
    *,
    query_kind: str,
    proof_gate_status: str,
    ambiguity_count: int,
    native_question_count: int,
    answer_candidate_count: int,
) -> SpeechActEligibility:
    """Return non-authoritative actuator eligibility for an unresolved response.

    This function never selects an act. In particular, ambiguity does not mean
    choose clarify. It may only make clarify physically/contextually eligible
    when native question content already exists. remain-silent is an affordance,
    not a default.
    """
    q = str(query_kind or "")
    gate = str(proof_gate_status or "")
    ambiguity = max(0, int(ambiguity_count))
    questions = max(0, int(native_question_count))
    answers = max(0, int(answer_candidate_count))

    expects_answer = q not in {"", "none", "unresolved-surface-question"}
    proof_blocked = (
        gate.startswith("proof-gated-")
        or "blocked" in gate
        or "missing" in gate
        or "ambigu" in gate
    )
    requires = bool(ambiguity or (expects_answer and answers == 0) or proof_blocked)
    if not requires:
        return SpeechActEligibility(
            requires_resolution=False,
            eligible_actions=(),
            reasons=("native-proof-path-does-not-require-resolution-act",),
            authority=_authority(),
        )

    actions = ["remain-silent"]
    reasons = []

    if expects_answer and answers == 0:
        actions.append("defer")
        reasons.append("answer-request-has-no-proof-eligible-answer")

    if questions > 0:
        actions.append("ask")
        reasons.append("native-question-content-already-exists")
        if ambiguity > 0:
            actions.append("clarify")
            reasons.append("unresolved-ambiguity-and-native-question-content-exist")
    elif ambiguity > 0:
        reasons.append("clarify-not-eligible-without-native-question-content")

    ordered = tuple(a for a in RESOLUTION_AFFORDANCES if a in set(actions))
    return SpeechActEligibility(
        requires_resolution=True,
        eligible_actions=ordered,
        reasons=tuple(reasons) or ("proof-gate-requires-resolution-without-authored-fallback",),
        authority=_authority(),
    )


def _authority() -> dict[str, bool]:
    return {
        "semantic_truth": False,
        "answer": False,
        "speech_act_selection": False,
        "candidate_ranking": False,
        "cognitive_memory": False,
        "relationship": False,
        "native_content_generation": False,
        "source_write": False,
        "deployment": False,
    }


def choose_resolution_act(
    *,
    eligible_actions: Sequence[str],
    context_geometry: object,
    action_pre_geometry: Mapping[str, object],
    action_post_geometry: Mapping[str, object],
    action_observations: Mapping[str, int],
    transport_fn: Callable[[object, object, object], object],
    reference_fn: Callable[[Mapping[str, object], Mapping[str, int], Iterable[str]], tuple[object | None, Sequence[str]]],
    distance_fn: Callable[[object, object], float],
    tied_fn: Callable[[float, float], bool],
) -> dict:
    """Select among eligible unresolved-response acts by learned consequences.

    No action is selected merely because it is the only programmed eligible action:
    a one-affordance set is infrastructure-forced and therefore cannot be reported
    as Yggdrasil's native choice.
    """
    eligible = tuple(dict.fromkeys(str(a) for a in eligible_actions if a))
    unknown = tuple(a for a in eligible if a not in RESOLUTION_AFFORDANCES)
    if unknown:
        raise ValueError(f"unknown resolution affordance(s): {unknown!r}")

    base_audit = {
        "eligible_actions": list(eligible),
        "native_choice_claim": False,
        "decision_layer": "unresolved",
        "candidate_distances": {},
        "predicted_post_states": {},
        "authority": {
            **_authority(),
            "speech_act_selection": True,
        },
        "selection_basis": "observed native consequence geometry only",
        "programmed_eligibility_is_choice": False,
    }

    if len(eligible) < 2:
        return {
            **base_audit,
            "action": None,
            "selection_status": "unresolved-insufficient-independent-affordances",
        }

    missing = tuple(
        a for a in eligible
        if action_pre_geometry.get(a) is None
        or action_post_geometry.get(a) is None
        or int(action_observations.get(a, 0)) < 1
    )
    if missing:
        return {
            **base_audit,
            "action": None,
            "selection_status": "unresolved-insufficient-speech-act-consequence-geometry",
            "missing_consequence_actions": list(missing),
        }

    reference, represented = reference_fn(
        action_post_geometry,
        action_observations,
        eligible,
    )
    represented = tuple(str(x) for x in represented)
    if reference is None or any(a not in represented for a in eligible):
        return {
            **base_audit,
            "action": None,
            "selection_status": "unresolved-incomplete-equal-affordance-reference",
            "represented_actions": list(represented),
        }

    predicted = {}
    distances = {}
    for action in eligible:
        post = transport_fn(
            action_pre_geometry[action],
            action_post_geometry[action],
            context_geometry,
        )
        predicted[action] = post
        distances[action] = float(distance_fn(post, reference))

    best = min(distances.values())
    winners = tuple(a for a, d in distances.items() if tied_fn(d, best))
    if len(winners) != 1:
        return {
            **base_audit,
            "action": None,
            "selection_status": "unresolved-exact-speech-act-consequence-geometry-tie",
            "candidate_distances": distances,
            "predicted_post_states": predicted,
            "tied_actions": list(winners),
        }

    return {
        **base_audit,
        "action": winners[0],
        "selection_status": "native-unique-speech-act-predicted-post-state-hs-minimum",
        "decision_layer": "learned-deliberative",
        "native_choice_claim": True,
        "candidate_distances": distances,
        "predicted_post_states": predicted,
    }
