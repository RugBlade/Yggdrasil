from __future__ import annotations

"""HF2 Milestone 4C1: structured resolution-content candidates.

This layer runs only after an unresolved-response speech act has a genuine
native-choice claim from consequence geometry. It does not select the act and it
does not assert truth. It forms bounded content candidates from information that
already exists in the current-turn native dialogue structure or from already
existing native question candidates.

Clarification surface grammar is deterministic realization only. The grammar does
not choose an ambiguity, referent, interpretation, answer, relationship meaning,
or whether Yggdrasil speaks. All unresolved alternatives are preserved.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ResolutionContentCandidate:
    act: str
    kind: str
    native_surface: str
    source_id: str
    alternatives: tuple[str, ...]
    source_units: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionContentPlan:
    selected_action: str | None
    native_choice_claim: bool
    candidates: tuple[ResolutionContentCandidate, ...]
    status: str
    authority: Mapping[str, bool]
    grammar_role: str


def _authority() -> dict[str, bool]:
    return {
        "semantic_truth": False,
        "answer": False,
        "speech_act_selection": False,
        "candidate_ranking": False,
        "ambiguity_resolution": False,
        "reference_resolution": False,
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


def _or_surface(alternatives: Sequence[str]) -> str:
    parts = [str(x).strip() for x in alternatives if str(x).strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} or {parts[1]}"
    return ", ".join(parts[:-1]) + f", or {parts[-1]}"


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

        surface = str(raw.get("surface") or "").strip()
        rendered_alternatives = _or_surface(alternatives)
        if kind == "reference" and surface:
            question = f"Does {surface} refer to {rendered_alternatives}?"
            source_units = (
                f"ambiguity:{ambiguity_id}",
                f"surface:{surface}",
                *(f"alternative:{x}" for x in alternatives),
            )
            content_kind = "reference-clarification"
        else:
            question = f"Which interpretation applies: {rendered_alternatives}?"
            source_units = (
                f"ambiguity:{ambiguity_id}",
                *(f"alternative:{x}" for x in alternatives),
            )
            content_kind = f"{kind}-clarification"

        out.append(
            ResolutionContentCandidate(
                act="clarify",
                kind=content_kind,
                native_surface=question,
                source_id=ambiguity_id,
                alternatives=alternatives,
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
                native_surface=q,
                source_id=f"native-question-{index}",
                alternatives=(),
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

    No parser label or programmed affordance may call this output Yggdrasil's
    chosen content. native_choice_claim here refers only to the upstream action
    selection. Candidate content remains an unranked bounded field.
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
            grammar_role="deterministic-structural-realization-only",
        )

    if action == "clarify":
        candidates = _clarification_candidates(dict(current_structure or {}))
        status = "clarification-candidates-preserve-all-unresolved-alternatives" if candidates else "clarify-selected-but-no-grounded-ambiguity-content"
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
        grammar_role="deterministic-structural-realization-only",
    )
