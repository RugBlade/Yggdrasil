from noeron.conversation_resolution import build_resolution_content


def _authority_zero(plan):
    for key in (
        "semantic_truth","answer","speech_act_selection","candidate_ranking",
        "ambiguity_resolution","reference_resolution","surface_authorship",
        "cognitive_memory","relationship","owner_preference","terra",
        "source_write","deployment",
    ):
        assert plan.authority[key] is False


def test_no_native_choice_means_no_resolution_content_even_with_ambiguity():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=False,
        current_structure={"ambiguities":[{"kind":"reference","surface":"she","candidates":["Mira","Sara"]}]},
    )
    assert plan.candidates == ()
    assert plan.status == "inactive-without-native-speech-act-choice"
    _authority_zero(plan)


def test_reference_clarification_preserves_focus_and_all_candidates_without_resolving_one():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[{"id":"ref-1","kind":"reference","surface":"she","candidates":["Mira","Sara"]}]},
    )
    assert len(plan.candidates)==1
    c=plan.candidates[0]
    assert c.focus_surface == "she"
    assert c.alternatives == ("Mira","Sara")
    assert c.existing_question == ""
    assert c.source_id == "ref-1"
    _authority_zero(plan)


def test_three_way_reference_ambiguity_preserves_every_alternative_without_surface_sentence():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[{"kind":"reference","surface":"they","alternatives":["A","B","C"]}]},
    )
    c=plan.candidates[0]
    assert c.alternatives == ("A","B","C")
    assert c.focus_surface == "they"
    assert c.existing_question == ""


def test_multiple_ambiguities_become_unranked_parallel_candidates():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[
            {"id":"a1","kind":"reference","surface":"it","candidates":["book","box"]},
            {"id":"a2","kind":"event-role","alternatives":["Mira-agent","Sara-agent"]},
        ]},
    )
    assert [c.source_id for c in plan.candidates] == ["a1","a2"]
    assert plan.authority["candidate_ranking"] is False
    assert plan.authority["ambiguity_resolution"] is False


def test_event_role_clarification_keeps_interpretations_as_structured_units():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[{"id":"role-1","kind":"event-role","alternatives":["agent=Mira","agent=Sara"]}]},
    )
    c=plan.candidates[0]
    assert c.kind == "event-role-clarification"
    assert c.alternatives == ("agent=Mira","agent=Sara")
    assert c.focus_surface == ""
    assert c.existing_question == ""


def test_resolved_or_empty_ambiguity_does_not_create_content():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[
            {"id":"done","kind":"reference","surface":"she","candidates":["Mira"],"resolved":True},
            {"id":"empty","kind":"reference","surface":"it","candidates":[]},
        ]},
    )
    assert plan.candidates == ()
    assert plan.status == "clarify-selected-but-no-grounded-ambiguity-content"


def test_ask_reuses_existing_native_questions_verbatim_only():
    questions=["What relation holds between lamp and room?","Why did Mira open the door?"]
    plan=build_resolution_content(
        selected_action="ask",native_choice_claim=True,
        existing_question_candidates=questions,
    )
    assert [c.existing_question for c in plan.candidates] == questions
    assert all(c.kind=="existing-native-question" for c in plan.candidates)
    _authority_zero(plan)


def test_ask_with_no_existing_native_question_does_not_author_fallback():
    plan=build_resolution_content(selected_action="ask",native_choice_claim=True)
    assert plan.candidates == ()
    assert plan.status == "ask-selected-but-no-existing-native-question-content"


def test_defer_does_not_invent_semantic_content():
    plan=build_resolution_content(selected_action="defer",native_choice_claim=True)
    assert plan.candidates == ()
    assert plan.status == "defer-is-nonsemantic-act-no-content-authored"
    _authority_zero(plan)


def test_remain_silent_does_not_invent_semantic_content():
    plan=build_resolution_content(selected_action="remain-silent",native_choice_claim=True)
    assert plan.candidates == ()
    assert plan.status == "remain-silent-is-nonsemantic-act-no-content-authored"
    _authority_zero(plan)


def test_duplicate_existing_native_questions_are_not_amplified():
    plan=build_resolution_content(
        selected_action="ask",native_choice_claim=True,
        existing_question_candidates=["Q?","Q?","R?"],
    )
    assert [c.existing_question for c in plan.candidates] == ["Q?","R?"]


def test_resolution_content_layer_never_claims_surface_authorship():
    plan=build_resolution_content(
        selected_action="clarify",native_choice_claim=True,
        current_structure={"ambiguities":[{"kind":"reference","surface":"it","candidates":["book","box"]}]},
    )
    assert plan.realization_role == "structured-content-only-no-surface-authorship"
    assert plan.authority["surface_authorship"] is False
    assert plan.authority["speech_act_selection"] is False
