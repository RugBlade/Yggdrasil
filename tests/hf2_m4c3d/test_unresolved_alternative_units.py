"""M4C3D typed current-turn alternative content; zero truth/choice authority."""
from uuid import uuid4

from noeron.cognition.models import (
    LanguageFacultyState, MathematicalProvenance, NativeThought, NativeThoughtKind,
)
from noeron.conversation_resolution import (
    native_current_turn_alternative_sources, native_resolution_sources,
    resolution_content_units,
)
from noeron.development import NativeLanguageFaculty
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.math.models import InferenceStep, LogicalProposition, LogicalQuery, MultiMemoryReasoningMathState


def kinds(rows):
    return [r.kind for r in rows]


def test_event_role_alternatives_are_explicit_parser_candidates_not_diagnostic_strings():
    structure=analyze_dialogue_structure('Mira gave Omar the book.')
    rows=structure['event_role_alternatives']
    assert [(r['role_slot'],r['surface'],r['candidates']) for r in rows]==[
        ('recipient_or_theme','omar',['recipient','theme']),
        ('theme_or_patient','book',['theme','patient']),
    ]
    assert all(r['authority']=='grammatical-event-role-candidate-only' for r in rows)
    clarifications,_=native_resolution_sources(structure)
    assert [(c.kind,c.focus_surface,c.alternatives) for c in clarifications]==[
        ('event-role-alternatives','omar',('recipient','theme')),
        ('event-role-alternatives','book',('theme','patient')),
    ]
    # The older proof-gate diagnostic remains visible, but is not itself content.
    assert any(a.get('alternatives')=='ditransitive-role-order-candidate' for a in structure['ambiguities'])
    assert all('ditransitive-role-order-candidate' not in c.alternatives for c in clarifications)


def test_event_role_content_requires_exact_same_parse_source_row():
    structure=analyze_dialogue_structure('Mira gave Omar the book.')
    structure['event_role_alternatives'][0]['candidates']=['recipient','invented-role']
    clarifications,_=native_resolution_sources(structure)
    assert all(c.source_id!='event-role-0-0-0' for c in clarifications)


def test_qud_alternatives_are_only_question_scoped_existing_ambiguity_options():
    structure=analyze_dialogue_structure('Where is she?',recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    rows=native_current_turn_alternative_sources(structure)
    assert kinds(rows)==['reference-alternatives','qud-alternatives']
    q=rows[1]
    assert q.focus_surface=='Where is she?'
    assert q.alternatives==('Sara','Mira')
    assert q.source_units[0]=='qud:question-sentence-0'
    assert q.source_units[1]=='unresolved-source:reference-token-2'
    assert not native_current_turn_alternative_sources(analyze_dialogue_structure('Where is Mira?'))


def test_multiple_proof_supported_propositions_are_preserved_without_ranking_or_assertion():
    reasoning=MultiMemoryReasoningMathState(
        logical_query=LogicalQuery(kind='relation-from-subject',raw='What is Mira?'),
        answer_candidates=[
            LogicalProposition(subject='mira',relation='is',object='scholar'),
            LogicalProposition(subject='mira',relation='is',object='teacher'),
        ],
        answer_selection_status='multiple-proof-supported-answers-no-forced-choice',
    )
    rows=native_current_turn_alternative_sources(analyze_dialogue_structure('What is Mira?'),reasoning)
    row=next(r for r in rows if r.kind=='proposition-alternatives')
    assert row.focus_surface=='What is Mira?'
    assert row.alternatives==('mira::is::scholar','mira::is::teacher')
    assert row.source_units[0].startswith('answer-selection-status:multiple-proof-supported')


def test_proposition_inventory_requires_explicit_multiple_no_forced_choice_status():
    reasoning=MultiMemoryReasoningMathState(
        logical_query=LogicalQuery(raw='What is Mira?'),
        answer_candidates=[
            LogicalProposition(subject='mira',relation='is',object='scholar'),
            LogicalProposition(subject='mira',relation='is',object='teacher'),
        ],
        answer_selection_status='unique-proof-supported-answer',
    )
    assert 'proposition-alternatives' not in kinds(
        native_current_turn_alternative_sources(analyze_dialogue_structure('What is Mira?'),reasoning))


def test_distinct_direct_proof_steps_for_same_conclusion_are_exact_json_alternatives():
    reasoning=MultiMemoryReasoningMathState(inference_steps=[
        InferenceStep(rule='modus-ponens',premises=['a::implies::b','a::true::true'],conclusion='b::true::true'),
        InferenceStep(rule='transitive',premises=['b::left::c','c::left::d'],conclusion='b::true::true'),
    ])
    rows=native_current_turn_alternative_sources(analyze_dialogue_structure('Explain.'),reasoning)
    row=next(r for r in rows if r.kind=='proof-alternatives')
    assert row.focus_surface=='b::true::true'
    assert row.alternatives==(
        '{"conclusion":"b::true::true","premises":["a::implies::b","a::true::true"],"rule":"modus-ponens"}',
        '{"conclusion":"b::true::true","premises":["b::left::c","c::left::d"],"rule":"transitive"}',
    )


def test_typed_native_units_serialize_zero_authority_and_realize_only_source_options():
    structure=analyze_dialogue_structure('Where is she?',recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    candidates=native_current_turn_alternative_sources(structure)
    event_id=uuid4()
    units=resolution_content_units(candidates,action='clarify',source_event_id=event_id)
    assert [u.kind for u in units]==['reference-alternatives','qud-alternatives']
    for u in units:
        dumped=u.model_dump()
        assert dumped['unresolved'] is True
        for key in ('semantic_truth_authority','answer_authority','candidate_ranking_authority',
                    'speech_act_selection_authority','reference_resolution_authority'):
            assert dumped[key] is False
    thought=NativeThought(kind=NativeThoughtKind.RESPONSE,statement='',resolution_content=units,
        mathematical_provenance=MathematicalProvenance(source_event_id=event_id))
    utterance=NativeLanguageFaculty().realize(thought,LanguageFacultyState())
    assert utterance.native_text=='she: Sara / Mira? Where is she?: Sara / Mira?'
    assert utterance.grammar_frames==[
        'native-resolution-reference-alternatives','native-resolution-qud-alternatives']


def test_inventory_never_turns_diagnostic_string_or_malformed_mapping_into_options():
    structure=analyze_dialogue_structure('Mira gave Omar the book.')
    structure['event_role_alternatives'][0]['candidates']='recipient or theme'
    structure['event_role_alternatives'][1]['candidates']={'theme':1,'patient':2}
    rows=native_current_turn_alternative_sources(structure)
    assert 'event-role-alternatives' not in kinds(rows)
    assert all('ditransitive-role-order-candidate' not in c.alternatives for c in rows)
