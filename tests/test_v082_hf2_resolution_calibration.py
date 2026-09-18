import pytest

from noeron.conversation_resolution import build_operator_resolution_calibration


def test_calibration_requires_authenticated_owner():
    plan=build_operator_resolution_calibration(
        action="ask",authenticated_owner=False,
        existing_question_candidates=["Existing native question?"],
    )
    assert plan.executable is False
    assert plan.status == "rejected-authenticated-owner-required"
    assert plan.authority["operator_execution"] is False
    assert plan.authority["native_choice"] is False
    assert plan.authority["relationship"] is False


def test_clarification_calibration_preserves_all_grounded_alternatives():
    plan=build_operator_resolution_calibration(
        action="clarify",authenticated_owner=True,
        current_structure={"ambiguities":[{
            "id":"ref-1","kind":"reference","surface":"she",
            "candidates":["Mira","Sara"],
        }]},
    )
    assert plan.executable is True
    assert plan.origin == "operator-directed-calibration-not-native-choice"
    assert plan.candidates[0].alternatives == ("Mira","Sara")
    assert plan.authority["native_choice"] is False
    assert plan.authority["preference_label"] is False
    assert plan.authority["relationship"] is False


def test_ask_calibration_reuses_existing_native_question_verbatim():
    question="What relation holds between lamp and room?"
    plan=build_operator_resolution_calibration(
        action="ask",authenticated_owner=True,
        existing_question_candidates=[question],
    )
    assert plan.executable is True
    assert [c.existing_question for c in plan.candidates] == [question]


def test_semantic_calibration_without_grounded_content_does_not_execute():
    clarify=build_operator_resolution_calibration(
        action="clarify",authenticated_owner=True,
    )
    ask=build_operator_resolution_calibration(
        action="ask",authenticated_owner=True,
    )
    assert clarify.executable is False
    assert ask.executable is False
    assert clarify.candidates == ()
    assert ask.candidates == ()


@pytest.mark.parametrize("action",["defer","remain-silent"])
def test_nonsemantic_calibration_authors_no_content(action):
    plan=build_operator_resolution_calibration(
        action=action,authenticated_owner=True,
    )
    assert plan.executable is True
    assert plan.candidates == ()
    assert plan.authority["semantic_truth"] is False
    assert plan.authority["answer"] is False
    assert plan.authority["surface_authorship"] is False


def test_unknown_calibration_act_is_rejected():
    with pytest.raises(ValueError):
        build_operator_resolution_calibration(
            action="answer",authenticated_owner=True,
        )
