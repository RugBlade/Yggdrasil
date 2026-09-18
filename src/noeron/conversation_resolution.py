from __future__ import annotations

"""HF2 Milestone 4C1: structured resolution-content candidates.

This layer runs only after an unresolved-response speech act has a genuine
native-choice claim from consequence geometry. It does not select the act, assert
truth, or author a human-language fallback sentence.

For clarification it preserves the current-turn unresolved focus and *all*
alternatives as structured content units. A later native-language stage may decide
how to realize those units using Yggdrasil's learned language machinery. For ask,
only already-existing native question content may pass through. Defer and
remain-silent author no semantic content.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ResolutionContentCandidate:
    act: str
    kind: str
    source_id: str
    focus_surface: str
    alternatives: tuple[str, ...]
    existing_question: str
    source_units: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionContentPlan:
    selected_action: str | None
    native_choice_claim: bool
    candidates: tuple[ResolutionContentCandidate, ...]
    status: str
    authority: Mapping[str, bool]
    realization_role: str


def _authority() -> dict[str, bool]:
    return {
        "semantic_truth": False,
        "answer": False,
        "speech_act_selection": False,
        "candidate_ranking": False,
        "ambiguity_resolution": False,
        "reference_resolution": False,
        "surface_authorship": False,
        "cognitive_memory": False,
        "relationship": False,
        "owner_preference": False,
        "terra": False,
        "source_write": False,
        "deployment": False,
    }


def _clean_alternatives(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, Iterable):
        values = tuple(str(x).strip() for x in raw if str(x).strip())
    else:
        values = ()
    return tuple(dict.fromkeys(x for x in values if x))


def _clarification_candidates(structure: Mapping[str, object]) -> tuple[ResolutionContentCandidate, ...]:
    out: list[ResolutionContentCandidate] = []
    for index, raw in enumerate(list(structure.get("ambiguities") or [])):
        if not isinstance(raw, Mapping) or bool(raw.get("resolved", False)):
            continue
        kind = str(raw.get("kind") or "unspecified")
        ambiguity_id = str(raw.get("id") or f"ambiguity-{index}")
        alternatives = _clean_alternatives(raw.get("alternatives") or raw.get("candidates") or ())
        if not alternatives:
            continue
        focus = str(raw.get("surface") or "").strip()
        source_units = (
            f"ambiguity:{ambiguity_id}",
            *((f"focus:{focus}",) if focus else ()),
            *(f"alternative:{x}" for x in alternatives),
        )
        out.append(
            ResolutionContentCandidate(
                act="clarify",
                kind=("reference-clarification" if kind == "reference" else f"{kind}-clarification"),
                source_id=ambiguity_id,
                focus_surface=focus,
                alternatives=alternatives,
                existing_question="",
                source_units=tuple(source_units),
            )
        )
    return tuple(out)


def _ask_candidates(existing_question_candidates: Sequence[str]) -> tuple[ResolutionContentCandidate, ...]:
    out: list[ResolutionContentCandidate] = []
    seen: set[str] = set()
    for index, raw in enumerate(existing_question_candidates):
        q = str(raw or "").strip()
        if not q or q in seen:
            continue
        seen.add(q)
        out.append(
            ResolutionContentCandidate(
                act="ask",
                kind="existing-native-question",
                source_id=f"native-question-{index}",
                focus_surface="",
                alternatives=(),
                existing_question=q,
                source_units=(f"existing-native-question:{index}",),
            )
        )
    return tuple(out)


def build_resolution_content(
    *,
    selected_action: str | None,
    native_choice_claim: bool,
    current_structure: Mapping[str, object] | None = None,
    existing_question_candidates: Sequence[str] = (),
) -> ResolutionContentPlan:
    """Form bounded content only for an already-native-selected act.

    native_choice_claim refers only to the upstream action selection. The candidate
    content field remains unranked and non-authoritative. This function never writes
    a new natural-language clarification/deference sentence.
    """
    action = str(selected_action or "").strip() or None
    authority = _authority()

    if not native_choice_claim or action is None:
        return ResolutionContentPlan(
            selected_action=action,
            native_choice_claim=False,
            candidates=(),
            status="inactive-without-native-speech-act-choice",
            authority=authority,
            realization_role="structured-content-only-no-surface-authorship",
        )

    if action == "clarify":
        candidates = _clarification_candidates(dict(current_structure or {}))
        status = "clarification-structure-preserves-all-unresolved-alternatives" if candidates else "clarify-selected-but-no-grounded-ambiguity-content"
    elif action == "ask":
        candidates = _ask_candidates(existing_question_candidates)
        status = "existing-native-question-candidates-preserved" if candidates else "ask-selected-but-no-existing-native-question-content"
    elif action in {"defer", "remain-silent"}:
        candidates = ()
        status = f"{action}-is-nonsemantic-act-no-content-authored"
    else:
        raise ValueError(f"unsupported resolution action: {action}")

    return ResolutionContentPlan(
        selected_action=action,
        native_choice_claim=True,
        candidates=candidates,
        status=status,
        authority=authority,
        realization_role="structured-content-only-no-surface-authorship",
    )


@dataclass(frozen=True)
class OperatorResolutionCalibrationExposure:
    action: str
    authenticated_owner: bool
    executable: bool
    candidates: tuple[ResolutionContentCandidate, ...]
    status: str
    origin: str
    authority: Mapping[str, bool]


def build_operator_resolution_calibration(
    *,
    action: str,
    authenticated_owner: bool,
    current_structure: Mapping[str, object] | None = None,
    existing_question_candidates: Sequence[str] = (),
) -> OperatorResolutionCalibrationExposure:
    """Expose one explicit owner calibration act from grounded current state only.

    Authentication grants operator authority to execute the requested actuator; it
    does not turn the request into Yggdrasil's choice, preference, or relationship
    state. Clarify and ask are executable only when their content already exists in
    the current structured/native field. Defer and remain-silent are nonsemantic
    acts and therefore carry no authored content.
    """
    action = str(action or "").strip()
    if action not in {"clarify", "ask", "defer", "remain-silent"}:
        raise ValueError("unsupported resolution calibration action")

    authority = {
        **_authority(),
        "operator_execution": bool(authenticated_owner),
        "authentication": bool(authenticated_owner),
        "native_choice": False,
        "preference_label": False,
    }
    if not authenticated_owner:
        return OperatorResolutionCalibrationExposure(
            action=action,
            authenticated_owner=False,
            executable=False,
            candidates=(),
            status="rejected-authenticated-owner-required",
            origin="unauthenticated-request-no-calibration-authority",
            authority=authority,
        )

    if action == "clarify":
        candidates = _clarification_candidates(dict(current_structure or {}))
        executable = bool(candidates)
        status = (
            "operator-directed-calibration-grounded-clarification-exposure"
            if executable else
            "calibration-not-executed-no-grounded-clarification-content"
        )
    elif action == "ask":
        candidates = _ask_candidates(existing_question_candidates)
        executable = bool(candidates)
        status = (
            "operator-directed-calibration-existing-native-question-exposure"
            if executable else
            "calibration-not-executed-no-existing-native-question-content"
        )
    else:
        candidates = ()
        executable = True
        status = f"operator-directed-calibration-{action}-nonsemantic-act"

    return OperatorResolutionCalibrationExposure(
        action=action,
        authenticated_owner=True,
        executable=executable,
        candidates=candidates,
        status=status,
        origin="operator-directed-calibration-not-native-choice",
        authority=authority,
    )
