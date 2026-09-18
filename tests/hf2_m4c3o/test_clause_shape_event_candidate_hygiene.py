from pathlib import Path

from noeron.inference import infer, parse_surface_logic_detailed
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def _analysis(text: str):
    return analyze_dialogue_structure(text)


def test_determiner_copular_clause_has_only_transparent_copular_candidate():
    a = _analysis("The lamp is on.")
    assert a["ambiguities"] == []
    assert a["event_role_alternatives"] == []
    assert len(a["event_candidates"]) == 1
    row = a["event_candidates"][0]
    assert row["voice"] == "copular-surface"
    assert row["predicate_surface"] == "is"
    assert row["roles"] == {"theme": "the lamp", "attribute_or_identity": "on"}
    assert row["authority"] == "candidate-only"


def test_known_lamp_turn_keeps_proof_support_without_dialogue_ambiguity():
    text = "The lamp is on. Is the lamp on?"
    a = _analysis(text)
    assert a["ambiguities"] == []
    assert a["event_role_alternatives"] == []
    props, query, _ = parse_surface_logic_detailed(text)
    answers = infer(props, query)[2]
    assert query.kind == "exact-proposition"
    assert [x.canonical() for x in answers] == ["lamp::is::on"]


def test_determiner_led_active_subject_does_not_become_verb():
    a = _analysis("The teacher opened the door.")
    assert a["ambiguities"] == []
    assert len(a["event_candidates"]) == 1
    row = a["event_candidates"][0]
    assert row["predicate_surface"] == "opened"
    assert row["roles"]["agent"] == "teacher"
    assert row["roles"]["patient_or_theme"] == "the door"
    assert row["authority"] == "candidate-only"


def test_direct_object_determiner_is_not_a_ditransitive_argument():
    a = _analysis("Teacher opened the door.")
    assert a["ambiguities"] == []
    assert a["event_role_alternatives"] == []
    assert len(a["event_candidates"]) == 1
    assert a["event_candidates"][0]["roles"] == {
        "agent": "teacher",
        "patient_or_theme": "the door",
    }


def test_genuine_double_object_surface_keeps_structural_alternatives():
    for text in ("Teacher gave Omar the book.", "The teacher gave Omar the book."):
        a = _analysis(text)
        assert any(
            x["kind"] == "event-role" and x["alternatives"] == "ditransitive-role-order-candidate"
            for x in a["ambiguities"]
        )
        assert len(a["event_role_alternatives"]) == 2
        assert {x["surface"] for x in a["event_role_alternatives"]} == {"omar", "book"}
        assert all(x["authority"] == "grammatical-event-role-candidate-only" for x in a["event_role_alternatives"])


def test_passive_surface_is_unchanged():
    a = _analysis("The book was placed by Mira.")
    assert a["ambiguities"] == []
    assert a["event_candidates"] == [{
        "sentence_index": 0,
        "event_index": 0,
        "predicate_surface": "placed",
        "predicate_lemma": "placed",
        "voice": "passive-surface",
        "roles": {"agent": "mira", "patient": "book"},
        "authority": "candidate-only",
    }]


def test_auxiliary_initial_copular_question_does_not_fake_active_declarative():
    a = _analysis("Is lamp on?")
    assert a["question_families"] == ["yes-no-question"]
    assert a["event_candidates"] == []
    assert a["ambiguities"] == []


def test_existing_oblique_ambiguity_remains_preserved():
    a = _analysis("Mira saw the scholar with the telescope.")
    assert any(
        x["kind"] == "event-role" and "instrument-or-comitative-or-attachment" in x["alternatives"]
        for x in a["ambiguities"]
    )
    assert any(x["relation_surface"] == "with" for x in a["event_role_alternatives"])


def test_runtime_lamp_turn_removes_fabricated_ambiguity_without_new_authority(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"))
    event = CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="authenticated-owner",
        content="The lamp is on. Is the lamp on?",
        trusted=True,
        metadata={"owner_authenticated": True, "owner_device_id": "m4c3o-test-owner"},
    )
    reply = n.ingest(event)
    assert reply.native_text == "lamp is on."
    assert reply.english_text == "Lamp is on."
    interp = reply.language_interpretation
    assert interp["ambiguity_count"] == 0
    structure = interp["structure"]
    assert structure["event_role_alternatives"] == []
    assert structure["semantic_truth_authority"] is False
    assert structure["answer_authority"] is False
    assert structure["speech_act_selection_authority"] is False
    assert structure["cognitive_memory_authority"] is False
    assert structure["relationship_authority"] is False
    assert structure["source_write_authority"] is False
    assert structure["deployment_authority"] is False
