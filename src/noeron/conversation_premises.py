"""HF2 bounded conversational premise substrate.

This module deliberately does *not* make dialogue into cognitive memory or truth.
It exposes a bounded, provenance-preserving working context that later native
IRG/DKT/EGR/RL/Frenet reasoning may inspect.  Serialization alone never grants
semantic, memory, relationship, answer, speech-act, or deployment authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Iterable, Literal, Sequence

PremiseOrigin = Literal[
    "current-turn",
    "bounded-dialogue-turn",
    "dkt-retrieved-persistent",
    "identity-substrate",
    "derived-inference",
]
PremiseStatus = Literal["active", "superseded", "conflict", "expired"]


@dataclass(frozen=True)
class NativeGeometryTrace:
    """Auditable native-machinery references attached to an eligible premise.

    Empty tuples are valid: a premise may exist in bounded dialogue before it has
    been activated by native reasoning.  These fields are evidence references,
    never proof merely by being present.
    """

    irg_event_ids: tuple[str, ...] = ()
    dkt_activation_ids: tuple[str, ...] = ()
    egr_region_ids: tuple[str, ...] = ()
    rl_proof_ids: tuple[str, ...] = ()
    frenet_trace_ids: tuple[str, ...] = ()

    @property
    def has_native_trace(self) -> bool:
        return bool(
            self.irg_event_ids
            or self.dkt_activation_ids
            or self.egr_region_ids
            or self.rl_proof_ids
            or self.frenet_trace_ids
        )


@dataclass(frozen=True)
class PremiseAuthority:
    """Authority boundary carried with every conversational premise."""

    cognitive_memory: bool = False
    semantic_truth: bool = False
    relationship: bool = False
    answer: bool = False
    speech_act: bool = False
    source_write: bool = False
    deployment: bool = False

    def assert_bounded_safe(self) -> None:
        if any(
            (
                self.cognitive_memory,
                self.semantic_truth,
                self.relationship,
                self.answer,
                self.speech_act,
                self.source_write,
                self.deployment,
            )
        ):
            raise ValueError("bounded conversational premise cannot acquire authority")


@dataclass
class ConversationalPremiseEnvelope:
    canonical: str
    subject: str
    relation: str
    object: str
    polarity: bool
    source_turn: int
    origin: PremiseOrigin
    admitted: bool = True
    status: PremiseStatus = "active"
    correction: bool = False
    confidence: float = 1.0
    authority: PremiseAuthority = field(default_factory=PremiseAuthority)
    native_trace: NativeGeometryTrace = field(default_factory=NativeGeometryTrace)
    supersedes: tuple[str, ...] = ()
    conflict_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_turn < 0:
            raise ValueError("source_turn must be non-negative")
        if not self.canonical.strip():
            raise ValueError("canonical premise is required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if self.origin in {"current-turn", "bounded-dialogue-turn"}:
            self.authority.assert_bounded_safe()

    @property
    def key(self) -> tuple[str, str, bool]:
        return (self.subject, self.relation, self.polarity)

    @property
    def contradiction_key(self) -> tuple[str, str]:
        return (self.subject, self.relation)


@dataclass(frozen=True)
class CurrentTurnAudit:
    turn: int
    input_sha256: str
    premise_canonicals: tuple[str, ...]
    ambiguity_count: int
    lexical_gap_count: int

    @classmethod
    def from_input(
        cls,
        *,
        turn: int,
        input_text: str,
        premise_canonicals: Sequence[str],
        ambiguity_count: int = 0,
        lexical_gap_count: int = 0,
    ) -> "CurrentTurnAudit":
        digest = sha256(input_text.encode("utf-8")).hexdigest()
        return cls(
            turn=turn,
            input_sha256=digest,
            premise_canonicals=tuple(premise_canonicals),
            ambiguity_count=int(ambiguity_count),
            lexical_gap_count=int(lexical_gap_count),
        )

    def matches(self, *, turn: int, input_text: str) -> bool:
        return self.turn == turn and self.input_sha256 == sha256(input_text.encode("utf-8")).hexdigest()


@dataclass
class BoundedConversationalPremiseContext:
    """Finite working context for dialogue premises.

    The context performs only bookkeeping/admission/conflict state.  It does not
    choose beliefs or answers.  Native IRG/DKT/EGR/RL/Frenet reasoning consumes
    eligible active premises in a later layer and must retain this provenance.
    """

    max_turns: int = 24
    premises: list[ConversationalPremiseEnvelope] = field(default_factory=list)
    current_audit: CurrentTurnAudit | None = None

    def _expire_before(self, newest_turn: int) -> None:
        floor = max(0, newest_turn - self.max_turns + 1)
        for p in self.premises:
            if p.source_turn < floor and p.status != "expired":
                p.status = "expired"

    def admit_turn(
        self,
        *,
        turn: int,
        input_text: str,
        premises: Iterable[ConversationalPremiseEnvelope],
        ambiguity_count: int = 0,
        lexical_gap_count: int = 0,
    ) -> CurrentTurnAudit:
        incoming = list(premises)
        for p in incoming:
            if p.source_turn != turn:
                raise ValueError("incoming premise source_turn must equal admitted turn")
            if p.origin != "current-turn":
                raise ValueError("new conversational premises must enter as current-turn")
            p.authority.assert_bounded_safe()

        self._expire_before(turn)
        self.premises.extend(incoming)
        self._classify_current_conflicts_and_corrections(turn)
        self.current_audit = CurrentTurnAudit.from_input(
            turn=turn,
            input_text=input_text,
            premise_canonicals=[p.canonical for p in incoming],
            ambiguity_count=ambiguity_count,
            lexical_gap_count=lexical_gap_count,
        )
        return self.current_audit

    def _classify_current_conflicts_and_corrections(self, turn: int) -> None:
        current = [p for p in self.premises if p.source_turn == turn and p.status == "active"]
        prior = [p for p in self.premises if p.source_turn < turn and p.status == "active"]

        for new in current:
            same_dimension = [
                old
                for old in prior + [p for p in current if p is not new]
                if old.contradiction_key == new.contradiction_key
                and (old.object != new.object or old.polarity != new.polarity)
                and old.status in {"active", "conflict"}
            ]
            if not same_dimension:
                continue

            if new.correction:
                superseded: list[str] = []
                for old in same_dimension:
                    old.status = "superseded"
                    superseded.append(old.canonical)
                new.supersedes = tuple(dict.fromkeys((*new.supersedes, *superseded)))
                new.status = "active"
            else:
                new.status = "conflict"
                refs = []
                for old in same_dimension:
                    if old.status != "superseded":
                        old.status = "conflict"
                        refs.append(old.canonical)
                        old.conflict_with = tuple(dict.fromkeys((*old.conflict_with, new.canonical)))
                new.conflict_with = tuple(dict.fromkeys((*new.conflict_with, *refs)))

    def eligible(self, *, include_conflicts: bool = True) -> tuple[ConversationalPremiseEnvelope, ...]:
        allowed = {"active", "conflict"} if include_conflicts else {"active"}
        out: list[ConversationalPremiseEnvelope] = []
        for p in self.premises:
            if not p.admitted or p.status not in allowed:
                continue
            if p.origin == "current-turn":
                p.origin = "bounded-dialogue-turn"
            out.append(p)
        return tuple(out)

    def require_fresh_audit(self, *, turn: int, input_text: str) -> CurrentTurnAudit:
        audit = self.current_audit
        if audit is None or not audit.matches(turn=turn, input_text=input_text):
            raise RuntimeError("stale current-turn interpretation/audit")
        return audit

    def authority_audit(self) -> dict[str, object]:
        return {
            "bounded_dialogue_is_cognitive_memory": False,
            "serialization_grants_truth": False,
            "owner_observation_grants_answer_authority": False,
            "native_reasoning_required_for_answer_selection": True,
            "native_path": "IRG->DKT->regional-EGR->RL/Frenet->DKT->native-cognition/action",
            "premise_count": len(self.premises),
        }
