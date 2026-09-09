from __future__ import annotations

from pathlib import Path

from noeron.cognition.models import NativeProposition, NativeThought, NativeThoughtKind, NativeUtterance
from noeron.english_egress import ENGLISH_EGRESS_VERSION, realize_native_thought
from noeron.inference import infer, parse_surface_logic_detailed
from noeron.language_dialogue import (
    CONVERSATION_VERSION, DIALOGUE_VERSION, PRODUCTIVE_ENGLISH_VERSION,
    analyze_dialogue_structure, lemma,
)
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def _n(tmp_path: Path) -> Noeron:
    return Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / "n.sqlite3"))


def _owner(text: str, **metadata) -> CognitiveEvent:
    m={"owner_authenticated":True,"owner_device_id":"test-owner-device"};m.update(metadata)
    return CognitiveEvent(kind=EventKind.USER_MESSAGE,source="authenticated-owner",content=text,trusted=True,metadata=m)


def test_01_v082_prospective_migration_and_versions(tmp_path: Path):
    n=_n(tmp_path);st=n.state.cognition.language
    assert st.version=="0.8.2" and st.v082_stage8b_started
    assert st.conversation_version==CONVERSATION_VERSION
    assert st.dialogue_version==DIALOGUE_VERSION
    assert st.productive_english_version==PRODUCTIVE_ENGLISH_VERSION
    assert st.english_egress_version==ENGLISH_EGRESS_VERSION
    assert st.dialogue.started_prospectively and st.dialogue.recent_turns==[]


def test_02_owner_communication_controls_default_off(tmp_path: Path):
    c=_n(tmp_path).owner_communication_controls()
    assert c["default_off"] is True
    assert c["internal_utterance_visibility"] is False
    assert c["internal_utterance_translation"] is False
    assert c["response_channel_override"] is False
    assert c["owner_command_channel"] is False
    assert c["cognitive_authority"] is False and c["relationship_authority"] is False


def test_03_owner_control_change_is_audited_not_native_choice(tmp_path: Path):
    n=_n(tmp_path);out=n.set_owner_communication_control("response_channel_override",True)
    assert out["response_channel_override"] is True and out["revision"]==1
    row=out["audit"][-1]
    assert row["origin"]=="authenticated-owner-command"
    assert row["native_choice_claim"] is False and row["relational_authority"] is False


def test_04_productive_morphology_normalizes_present_agreement_without_truth_authority():
    assert lemma("contains")=="contain"
    assert lemma("supports")=="support"
    a=analyze_dialogue_structure("Mira contains copper.")
    assert any(x["surface"]=="contains" and x["lemma"]=="contain" for x in a["morphology"])
    assert a["semantic_truth_authority"] is False


def test_05_event_candidates_expose_semantic_roles_as_candidates_only():
    a=analyze_dialogue_structure("Mira placed the book beside the lamp.")
    assert a["event_candidates"]
    assert all(x["authority"]=="candidate-only" for x in a["event_candidates"])
    assert any("agent" in x["roles"] for x in a["event_candidates"])


def test_06_passive_candidate_does_not_gain_truth_authority():
    a=analyze_dialogue_structure("The book was placed by Mira.")
    p=next(x for x in a["event_candidates"] if x["voice"]=="passive-surface")
    assert p["roles"]["agent"]=="mira" and p["roles"]["patient"]=="book"
    assert p["authority"]=="candidate-only"


def test_07_unknown_words_are_explicit_lexical_gaps():
    a=analyze_dialogue_structure("The quorvex supports the lamp.",lexicon={"lamp":object(),"supports":object()})
    gaps={x["surface"] for x in a["lexical_gaps"]}
    assert "quorvex" in gaps
    assert all(x["authority"]=="unknown-word-representation-only" for x in a["lexical_gaps"])


def test_08_ambiguity_is_preserved_as_alternatives():
    a=analyze_dialogue_structure("Mira saw the scholar with the telescope.")
    assert any(x["kind"]=="event-role" and "instrument-or-comitative-or-attachment" in x["alternatives"] for x in a["ambiguities"])


def test_09_dialogue_state_is_bounded_working_context_not_cognitive_memory(tmp_path: Path):
    n=_n(tmp_path)
    n.ingest(_owner("Mira placed the book beside the lamp."))
    d=n.language_dialogue_state()
    assert d["turn"]==1 and d["recent_turns"]
    assert d["cognitive_memory_authority"] is False
    assert d["legacy_stage6_discourse_distinct"] is True


def test_10_language_structure_probe_is_read_only(tmp_path: Path):
    n=_n(tmp_path);before=n.language_state()
    out=n.language_structure("If Mira leaves, then Omar waits.",owner_authenticated=True)
    after=n.language_state()
    assert out["state_changed"] is False
    assert before["lessons_observed"]==after["lessons_observed"]
    assert before["sentences_observed"]==after["sentences_observed"]
    assert before["proposition_count"]==after["proposition_count"]
    assert before["dialogue"]["turn"]==after["dialogue"]["turn"]


def test_11_who_query_is_productive_and_proof_supported():
    props,q,_=parse_surface_logic_detailed("Mira placed the book. Who placed the book?")
    derived,steps,candidates,status=infer(props,q)
    assert q.kind=="relation-to-object"
    assert status=="unique-proof-supported-answer"
    assert [(x.subject,x.relation,x.object) for x in candidates]==[("mira","placed","book")]


def test_12_what_query_matches_transparent_past_base_morphology():
    props,q,_=parse_surface_logic_detailed("Mira placed the book. What did Mira place?")
    candidates=infer(props,q)[2]
    assert q.kind=="relation-from-subject" and q.relation=="place"
    assert len(candidates)==1 and candidates[0].object=="book"


def test_13_yes_no_query_returns_supported_proposition_not_canned_yes():
    props,q,_=parse_surface_logic_detailed("Mira contains copper. Does Mira contain copper?")
    candidates=infer(props,q)[2]
    assert q.kind=="exact-proposition" and len(candidates)==1
    assert candidates[0].canonical().find("mira")>=0


def test_14_why_query_returns_only_existing_proof_ground_candidate():
    props,q,_=parse_surface_logic_detailed("Mira is a scholar. Why is Mira a scholar?")
    candidates=infer(props,q)[2]
    assert q.kind=="why-proposition" and len(candidates)==1
    props2,q2,_=parse_surface_logic_detailed("Why is Mira a scholar?")
    assert infer(props2,q2)[2]==[]


def test_15_how_when_do_not_invent_unsupported_relations():
    for text in ("How did Mira travel?","When did Mira travel?"):
        props,q,_=parse_surface_logic_detailed(text)
        assert q.kind in {"how-from-subject","when-from-subject"}
        assert infer(props,q)[2]==[]


def test_16_english_egress_only_realizes_existing_native_propositions():
    p=NativeProposition(subject="Mira",relation="supports",object="Omar",grounds=["direct"],confidence=1.0)
    t=NativeThought(kind=NativeThoughtKind.RESPONSE,statement="",propositions=[p])
    u=NativeUtterance(native_text="Mira supports Omar.")
    text,audit=realize_native_thought(t,u)
    assert text=="Mira supports Omar."
    assert audit["source_proposition_count"]==1
    assert audit["content_authority"] is False and audit["answer_authority"] is False and audit["terra_authority"] is False


def test_17_english_egress_removes_boolean_serialization_artifact_without_adding_content():
    p=NativeProposition(subject="build",relation="failed",object="true",grounds=["direct"],confidence=1.0)
    t=NativeThought(kind=NativeThoughtKind.RESPONSE,statement="",propositions=[p])
    text,audit=realize_native_thought(t,NativeUtterance(native_text="build failed true."))
    assert text=="Build failed."
    assert audit["source_proposition_count"]==1 and len(audit["source_units"])==1


def test_18_unresolved_native_communication_does_not_surface_by_fallback(tmp_path: Path):
    n=_n(tmp_path)
    r=n.ingest(_owner("Every glorp is a blin. Mavo is a glorp. What follows?"))
    assert r.native_text
    assert r.text==""
    assert r.communication_native_choice_claim is False
    assert r.communication_selection_status=="unresolved-insufficient-consequence-geometry"
    assert r.transport_origin=="none"


def test_19_authenticated_response_override_transports_existing_content_without_native_choice_claim(tmp_path: Path):
    n=_n(tmp_path);n.set_owner_communication_control("response_channel_override",True)
    r=n.ingest(_owner("Every glorp is a blin. Mavo is a glorp. What follows?"))
    assert r.native_text and r.english_text and r.text==r.english_text
    assert r.transport_origin=="authenticated-owner-response-channel-override"
    assert r.communication_native_choice_claim is False
    assert n.state.cognition.initiative_development.pending_expression_event_id is None


def test_20_owner_command_channel_is_task_authority_and_transport_not_relationship_or_native_choice(tmp_path: Path):
    n=_n(tmp_path);n.set_owner_communication_control("owner_command_channel",True)
    r=n.ingest(_owner("Every glorp is a blin. Mavo is a glorp. What follows?",owner_command=True))
    assert r.text and r.transport_origin=="authenticated-owner-command-response-transport"
    audit=n.state.cognition.language.last_communication_audit
    assert audit["owner_command_authority"] is True
    assert audit["native_choice_claim"] is False
    assert n.state.cognition.language.owner_communication_controls.relationship_authority is False


def test_21_owner_can_privately_observe_internal_utterance_without_forcing_surface(tmp_path: Path):
    n=_n(tmp_path)
    n.set_owner_communication_control("internal_utterance_visibility",True)
    r=n.ingest(_owner("Every glorp is a blin. Mavo is a glorp. What follows?"))
    assert r.native_text and r.text==""
    before=dict(n.state.cognition.language.last_communication_audit)
    obs=n.owner_internal_utterance_observation()
    after=dict(n.state.cognition.language.last_communication_audit)
    assert obs["status"]=="available" and obs["native_text"]==r.native_text
    assert obs["english_translation"]==""
    assert obs["outward_text_present"] is False
    assert obs["observation_changes_communication_action"] is False
    assert obs["communication_authority"] is False and obs["cognitive_memory_authority"] is False
    assert before==after


def test_22_owner_can_enable_deterministic_translation_of_private_internal_utterance(tmp_path: Path):
    n=_n(tmp_path)
    n.set_owner_communication_control("internal_utterance_visibility",True)
    n.set_owner_communication_control("internal_utterance_translation",True)
    r=n.ingest(_owner("Every glorp is a blin. Mavo is a glorp. What follows?"))
    assert r.native_text and r.english_text and r.text==""
    obs=n.owner_internal_utterance_observation()
    assert obs["native_text"]==r.native_text
    assert obs["english_translation"]==r.english_text
    assert obs["translation_deterministic"] is True
    assert obs["translation_content_authority"] is False
    assert obs["communication_native_choice_claim"] is False
    assert obs["transport_origin"]=="none"
