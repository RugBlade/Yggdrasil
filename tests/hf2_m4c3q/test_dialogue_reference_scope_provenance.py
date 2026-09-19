from pathlib import Path

from noeron.language_dialogue import analyze_dialogue_structure, referent_mentions
from noeron.llm import MockLanguageEngine
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def _recent(text: str):
    return referent_mentions(analyze_dialogue_structure(text))


def _owner(text: str) -> CognitiveEvent:
    return CognitiveEvent(
        kind=EventKind.USER_MESSAGE,
        source="authenticated-owner",
        content=text,
        trusted=True,
        metadata={"owner_authenticated": True, "owner_device_id": "m4c3q-focused"},
    )


def test_same_ingress_copular_reference_uses_prior_sentence_only():
    a = analyze_dialogue_structure("The lamp is on. Is it on?")
    assert a["reference_candidates"] == [{
        "surface": "it", "token_index": 5, "candidates": ["the lamp"],
        "status": "resolved-unique-candidate", "authority": "grammatical-reference-candidate-only",
        "sentence_index": 1, "id": "reference-token-5",
    }]
    assert a["ambiguities"] == []


def test_same_ingress_transitive_reference_uses_prior_sentence():
    a = analyze_dialogue_structure("Mira opened the door. Is it open?")
    ref = a["reference_candidates"][0]
    assert ref["candidates"] == ["the door"]
    assert ref["sentence_index"] == 1
    assert ref["token_index"] == 5


def test_same_ingress_person_uncertainty_is_not_guessed_away():
    a = analyze_dialogue_structure("Mira opened the door. Did she close it?")
    refs = {x["surface"]: x for x in a["reference_candidates"]}
    assert refs["she"]["candidates"] == ["the door", "mira"]
    assert refs["she"]["status"] == "ambiguous-alternatives-preserved"
    assert refs["it"]["candidates"] == ["the door"]
    assert any(x["kind"] == "reference" and x["surface"] == "she" for x in a["ambiguities"])


def test_prior_turn_prepositional_copular_complement_is_not_nominal_antecedent():
    a = analyze_dialogue_structure("Is it on?", recent_referents=_recent("The lamp is on."))
    assert a["reference_candidates"][0]["candidates"] == ["the lamp"]
    assert a["ambiguities"] == []


def test_prior_turn_spatial_prepositional_complement_is_not_nominal_antecedent():
    a = analyze_dialogue_structure("Where is it?", recent_referents=_recent("The book is on the table."))
    assert a["reference_candidates"][0]["candidates"] == ["the book"]
    assert a["ambiguities"] == []


def test_nominal_copular_complement_remains_candidate_without_semantic_typing():
    a = analyze_dialogue_structure("Is she kind?", recent_referents=_recent("Mira is a scholar."))
    ref = a["reference_candidates"][0]
    assert ref["candidates"] == ["a scholar", "mira"]
    assert ref["status"] == "ambiguous-alternatives-preserved"


def test_prior_turn_transitive_reference_control_is_unchanged():
    a = analyze_dialogue_structure("Is it open?", recent_referents=_recent("Mira opened the door."))
    assert a["reference_candidates"][0]["candidates"] == ["the door"]
    assert a["ambiguities"] == []


def test_genuine_multi_referent_person_ambiguity_is_preserved():
    a = analyze_dialogue_structure("Did she leave?", recent_referents=_recent("Mira met Sara."))
    ref = a["reference_candidates"][0]
    assert ref["candidates"] == ["sara", "mira"]
    assert ref["status"] == "ambiguous-alternatives-preserved"


def test_same_ingress_multiple_nominal_candidates_remain_ambiguous():
    a = analyze_dialogue_structure("Mira placed the book beside the lamp. Is it blue?")
    ref = a["reference_candidates"][0]
    assert ref["candidates"] == ["the lamp", "the book beside the lamp"]
    assert ref["status"] == "ambiguous-alternatives-preserved"


def test_current_sentence_cannot_resolve_itself_without_prior_context():
    a = analyze_dialogue_structure("Is it on?")
    ref = a["reference_candidates"][0]
    assert ref["candidates"] == []
    assert ref["status"] == "unresolved-no-candidate"


def test_runtime_unique_reference_allows_existing_proof_path_without_parser_authority(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"), terra_enabled=False)
    reply = n.ingest(_owner("The lamp is on. Is it on?"))
    query = n.state.math_kernel.reasoning.logical_query
    assert (query.kind, query.subject, query.relation, query.object) == ("exact-proposition", "lamp", "is", "on")
    assert n.state.math_kernel.reasoning.proof_gate_status == "proof-gate-all-candidates-auditable"
    assert reply.native_text == "lamp is on."
    structure = reply.language_interpretation["structure"]
    assert structure["ambiguities"] == []
    assert structure["semantic_truth_authority"] is False
    assert structure["answer_authority"] is False
    assert structure["speech_act_selection_authority"] is False


def test_runtime_genuine_reference_ambiguity_remains_nonanswering(tmp_path: Path):
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"), terra_enabled=False)
    n.ingest(_owner("Mira met Sara."))
    reply = n.ingest(_owner("Did she leave?"))
    structure = reply.language_interpretation["structure"]
    assert any(x["kind"] == "reference" and x["surface"] == "she" for x in structure["ambiguities"])
    assert reply.native_text == ""
    assert structure["semantic_truth_authority"] is False
    assert structure["answer_authority"] is False
