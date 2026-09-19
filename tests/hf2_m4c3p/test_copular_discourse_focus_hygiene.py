from pathlib import Path

from noeron.inference import parse_surface_logic_detailed
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def _event(text: str) -> CognitiveEvent:
    return CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="authenticated-owner",
        content=text,
        trusted=True,
        metadata={"owner_authenticated": True, "owner_device_id": "m4c3p-focused"},
    )


def _parse(text: str):
    return parse_surface_logic_detailed(text)


def test_copular_predicate_complement_is_not_direct_object_focus():
    props, query, audit = _parse("The lamp is on. Is it on?")
    assert [p.canonical() for p in props] == ["lamp::is::on"]
    assert (query.kind, query.subject, query.relation, query.object) == (
        "exact-proposition", "lamp", "is", "on"
    )
    assert audit["resolutions"] == [{"surface": "it", "resolved_to": "lamp", "role": "query-subject"}]
    assert audit["last_subject"] == "lamp"
    assert audit["last_direct_object"] == ""
    assert {tuple(sorted(x.items())) for x in audit["mentions"]} >= {
        tuple(sorted({"entity": "lamp", "role": "subject"}.items())),
        tuple(sorted({"entity": "on", "role": "predicate-complement"}.items())),
    }


def test_why_pronoun_targets_copular_subject_without_self_explanation():
    props, query, audit = _parse("The lamp is on. Why is it on?")
    assert [p.canonical() for p in props] == ["lamp::is::on"]
    assert (query.kind, query.subject, query.relation, query.object) == (
        "why-proposition", "lamp", "is", "on"
    )
    assert audit["last_direct_object"] == ""


def test_property_question_keeps_copular_subject_as_pronoun_target():
    _props, query, audit = _parse("The lamp is red. What color is it?")
    assert (query.kind, query.subject, query.relation, query.object) == (
        "copular-value-from-subject", "lamp", "is", "color"
    )
    assert audit["last_direct_object"] == ""


def test_transitive_direct_object_focus_is_preserved():
    _props, query, audit = _parse("Mira opened the door. Is it open?")
    assert (query.kind, query.subject, query.relation, query.object) == (
        "exact-proposition", "door", "is", "open"
    )
    assert audit["last_direct_object"] == "door"


def test_newer_spatial_copular_clause_clears_stale_transitive_object_focus():
    _props, query, audit = _parse(
        "Mira opened the door. The book is on the table. Where is it?"
    )
    assert (query.kind, query.subject) == ("relation-from-subject", "book")
    assert audit["last_subject"] == "book"
    assert audit["last_direct_object"] == ""
    assert audit["last_oblique_object"] == "table"


def test_relative_copular_predicate_is_not_direct_object_focus():
    _props, query, audit = _parse("The book that Mira placed is blue. What color is it?")
    assert (query.kind, query.subject, query.relation, query.object) == (
        "copular-value-from-subject", "book", "is", "color"
    )
    assert audit["last_direct_object"] == ""


def test_runtime_keeps_reference_authority_separate_after_target_fix(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"), terra_enabled=False)
    reply = n.ingest(_event("The lamp is on. Is it on?"))
    query = n.state.math_kernel.reasoning.logical_query
    assert (query.kind, query.subject, query.relation, query.object) == (
        "exact-proposition", "lamp", "is", "on"
    )
    structure = reply.language_interpretation["structure"]
    assert structure["semantic_truth_authority"] is False
    assert structure["answer_authority"] is False
    assert structure["speech_act_selection_authority"] is False

    # M4C3P originally exposed a separate language_dialogue ambiguity after fixing
    # the logical/QUD target.  A later transparent reference-hygiene milestone may
    # remove that demonstrably malformed ambiguity.  The enduring M4C3P invariant
    # is authority separation: unresolved ambiguity blocks; resolved structure may
    # proceed only through the existing proof gate, never through parser authority.
    if structure["ambiguities"]:
        assert n.state.math_kernel.reasoning.proof_gate_status == "proof-gated-unresolved-ambiguity"
        assert reply.native_text == ""
        assert reply.english_text == ""
    else:
        assert n.state.math_kernel.reasoning.proof_gate_status == "proof-gate-all-candidates-auditable"
        assert reply.native_text == "lamp is on."


def test_derived_why_control_remains_proof_auditable(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"), terra_enabled=False)
    n.ingest(_event("If the lamp is on, the room is bright. The lamp is on."))
    reply = n.ingest(_event("Why is the room bright?"))
    query = n.state.math_kernel.reasoning.logical_query
    assert (query.kind, query.subject, query.relation, query.object) == (
        "why-proposition", "room", "is", "bright"
    )
    assert n.state.math_kernel.reasoning.proof_gate_status == "proof-gate-why-support-auditable"
    assert "lamp is on." in reply.native_text
    assert reply.language_interpretation["authority"]["answer"] is False


def test_prior_turn_transitive_wh_control_remains_answerable(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"), terra_enabled=False)
    n.ingest(_event("Mira opened the door."))
    reply = n.ingest(_event("What did Mira open?"))
    query = n.state.math_kernel.reasoning.logical_query
    assert (query.kind, query.subject, query.relation) == ("relation-from-subject", "mira", "open")
    assert n.state.math_kernel.reasoning.proof_gate_status == "proof-gate-all-candidates-auditable"
    assert reply.native_text == "mira opened door."
