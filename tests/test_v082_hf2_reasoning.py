from noeron.inference import parse_surface_logic_detailed, infer


def run(text: str):
    props, query, audit = parse_surface_logic_detailed(text, {})
    derived, steps, answers, status = infer(props, query)
    return props, query, audit, derived, steps, answers, status


def canon(rows):
    return [p.canonical() for p in rows]


def test_hf2_copular_yes_no_positive_and_negative_are_structurally_aligned():
    _, q1, _, _, _, a1, s1 = run("The lamp is on. Is the lamp on?")
    assert q1.kind == "exact-proposition"
    assert canon(a1) == ["lamp::is::on"]
    assert s1 == "unique-proof-supported-answer"

    _, q2, _, _, _, a2, s2 = run("The lamp is not on. Is the lamp on?")
    assert q2.kind == "exact-proposition"
    assert canon(a2) == ["not lamp::is::on"]
    assert s2 == "unique-proof-supported-negative-answer"


def test_hf2_copular_spatial_relation_becomes_typed_binary_proposition():
    props, q, _, _, _, answers, status = run(
        "A red book is on the table. What is on the table?"
    )
    assert canon(props) == ["red book::on::table"]
    assert q.kind == "relation-to-object" and q.relation == "on" and q.object == "table"
    assert canon(answers) == ["red book::on::table"]
    assert status == "unique-proof-supported-answer"


def test_hf2_property_query_preserves_multiple_values_without_forced_choice():
    _, q1, _, _, _, one, s1 = run("The box is blue. What color is the box?")
    assert q1.kind == "copular-value-from-subject"
    assert canon(one) == ["box::is::blue"]
    assert s1 == "unique-proof-supported-answer"

    _, _, _, _, _, many, s2 = run(
        "The box is red. The box is blue. What color is the box?"
    )
    assert set(canon(many)) == {"box::is::red", "box::is::blue"}
    assert s2 == "multiple-proof-supported-answers-no-forced-choice"


def test_hf2_explicit_correction_supersedes_only_bounded_same_relation_for_answering():
    from noeron.inference import proposition_key
    from noeron.math import dkt
    from noeron.reasoning import build_multi_memory_reasoning

    props, query, _ = parse_surface_logic_detailed(
        "The box is red. Correction: the box is blue. What color is the box?", {}
    )
    result = infer(props, query)
    _, steps, answers, status = result
    assert set(canon(props)) == {"box::is::red", "box::is::blue"}
    assert any("correction" in p.modifiers for p in props)
    assert canon(answers) == ["box::is::blue"]
    assert status == "unique-proof-supported-answer"

    # M4C3S keeps premise admission auditable without turning it into a proof.
    # Retain the evidence-bearing result rather than discard it on unpacking.
    assert result.admission_audit == [{
        "kind": "bounded-correction-supersession",
        "old_key": proposition_key(props[0]),
        "new_key": proposition_key(props[1]),
        "removed_input_indexes": [0],
        "control_input_index": 1,
        "role": "admission-event-not-formal-proof",
        "semantic_truth_authority": False,
        "answer_authority": False,
    }]
    assert result.admitted_indexes == [1]
    assert not steps
    assert not result.ledger.records
    assert result.ledger.proof_ledger_complete

    reasoning = build_multi_memory_reasoning(
        dkt.reference_knot(), [], logical_propositions=props, logical_query=query,
    )
    assert reasoning.proof_admission_audit == result.admission_audit
    assert canon(reasoning.answer_candidates) == ["box::is::blue"]
    assert not reasoning.inference_steps
    restored = type(reasoning).model_validate_json(reasoning.model_dump_json())
    assert restored.proof_admission_audit == reasoning.model_dump(mode="json")["proof_admission_audit"]

    # The corrected target cannot explain itself through an admission event.
    why = query.model_copy(update={"kind": "why-proposition", "object": "blue"})
    explanation = infer(props, why)
    assert explanation.admission_audit == result.admission_audit
    assert not explanation.candidates
    assert explanation.status == "no-proof-supported-answer"
    why_reasoning = build_multi_memory_reasoning(
        dkt.reference_knot(), [], logical_propositions=props, logical_query=why,
    )
    assert why_reasoning.proof_admission_audit == result.admission_audit
    assert not why_reasoning.answer_candidates
    assert not why_reasoning.autonomous_proof_candidates


def test_hf2_natural_conditional_enters_structured_modus_ponens():
    props, q, audit, derived, steps, answers, status = run(
        "If the lamp is on, the room is bright. The lamp is on. Is the room bright?"
    )
    assert any(p.relation == "implies-proposition" for p in props)
    assert audit.get("structured_conditionals")
    assert any(s.rule == "structured-modus-ponens" for s in steps)
    assert "room::is::bright" in canon(derived)
    assert canon(answers) == ["room::is::bright"]
    assert status == "unique-proof-supported-answer"


def test_hf2_comparative_relation_has_generic_relation_subject_query():
    props, q, _, _, _, answers, status = run(
        "The red box is larger than the blue box. Which box is larger?"
    )
    assert canon(props) == ["red box::larger-than::blue box"]
    assert q.kind == "relation-subjects" and q.relation == "larger-than"
    assert canon(answers) == ["red box::larger-than::blue box"]
    assert status == "unique-proof-supported-answer"


def test_hf2_event_truth_is_not_itself_a_why_answer():
    props, q, _, _, steps, answers, status = run(
        "Mira opened the door. Why did Mira open the door?"
    )
    assert canon(props) == ["mira::opened::door"]
    assert q.kind == "why-proposition"
    assert not steps
    assert answers == []
    assert status == "no-proof-supported-answer"


def test_hf2_why_can_use_an_actual_derivation_as_explanatory_support():
    _, q, _, _, steps, answers, status = run(
        "If the lamp is on, the room is bright. The lamp is on. Why is the room bright?"
    )
    assert q.kind == "why-proposition"
    assert any(
        s.rule == "structured-modus-ponens" and s.conclusion == "room::is::bright"
        for s in steps
    )
    assert len(answers) >= 1
    assert "lamp::is::on" in canon(answers)
    assert status in {
        "multiple-proof-supported-answers-no-forced-choice",
        "unique-proof-supported-answer",
    }
