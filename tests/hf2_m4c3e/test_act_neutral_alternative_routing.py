"""M4C3E act-neutral unresolved content routing; choice stays native geometry only."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from noeron.cognition import models as cm
from noeron.conversation_actions import choose_resolution_act, resolution_affordances
from noeron.conversation_resolution import (
    native_current_turn_alternative_sources, resolution_content_units,
)
from noeron.development import NativeLanguageFaculty
from noeron.language_dialogue import analyze_dialogue_structure
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.math.models import InferenceStep, LogicalProposition, LogicalQuery, MultiMemoryReasoningMathState
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def multi_answer_reasoning():
    return MultiMemoryReasoningMathState(
        logical_query=LogicalQuery(kind='relation-from-subject',raw='What is Mira?'),
        answer_candidates=[
            LogicalProposition(subject='mira',relation='is',object='scholar'),
            LogicalProposition(subject='mira',relation='is',object='teacher'),
        ],
        answer_selection_status='multiple-proof-supported-answers-no-forced-choice',
        proof_gate_status='proof-support-gate-passed',
    )


def seed_speech_geometry(n, target='ask'):
    context=n.state.math_kernel.dkt.core_knot
    st=n.state.cognition.speech_act_development
    for i,a in enumerate(('clarify','ask','defer','remain-silent'),1):
        pre=context.model_copy(deep=True)
        if a != target:
            pre.c0[0] += i*.2
        pre.invariant_signature=dkt.invariant_signature(pre)
        st.action_pre_knots[a]=pre
        st.action_post_knots[a]=context.model_copy(deep=True)
        st.action_observations[a]=1
    st.transition_observations=4


def test_qud_proposition_and_proof_inventory_is_act_neutral_and_carries_no_choice():
    structure=analyze_dialogue_structure('Where is she?',recent_referents=[
        {'surface':'Mira','kind':'person'},{'surface':'Sara','kind':'person'}])
    reasoning=multi_answer_reasoning()
    reasoning.inference_steps=[
        InferenceStep(rule='r1',premises=['a::true::true'],conclusion='mira::is::scholar'),
        InferenceStep(rule='r2',premises=['b::true::true'],conclusion='mira::is::scholar'),
    ]
    rows=native_current_turn_alternative_sources(structure,reasoning)
    neutral=[r for r in rows if r.kind in {'qud-alternatives','proposition-alternatives','proof-alternatives'}]
    assert neutral
    assert all(r.act=='' and r.compatible_actions==('clarify','ask') for r in neutral)
    event_id=uuid4()
    for action in ('clarify','ask'):
        units=resolution_content_units(neutral,action=action,source_event_id=event_id)
        assert units and all(u.act==action for u in units)
        assert all(u.speech_act_selection_authority is False for u in units)
        thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='',resolution_content=units,
            mathematical_provenance=cm.MathematicalProvenance(source_event_id=event_id))
        utterance=NativeLanguageFaculty().realize(thought,cm.LanguageFacultyState())
        assert utterance.native_text
        assert 'Do you mean' not in utterance.native_text
        assert all(f.startswith('native-resolution-') for f in utterance.grammar_frames)
        if action=='ask':
            assert all(f.startswith('native-resolution-ask-') for f in utterance.grammar_frames)


def test_act_neutral_content_opens_both_question_like_affordances_but_never_selects_one():
    e=resolution_affordances(
        query_kind='relation-from-subject',proof_gate_status='proof-support-gate-passed',
        ambiguity_count=0,native_question_count=0,answer_candidate_count=2,
        native_clarification_count=0,act_neutral_alternative_count=1,
    )
    assert e.requires_resolution is True
    assert e.eligible_actions==('clarify','ask','remain-silent')
    assert 'act-neutral-unresolved-alternative-content-exists' in e.reasons
    assert e.authority['speech_act_selection'] is False
    out=choose_resolution_act(
        eligible_actions=e.eligible_actions,context_geometry=0.0,
        action_pre_geometry={},action_post_geometry={},action_observations={},
        transport_fn=lambda pre,post,current: current,
        reference_fn=lambda posts,obs,acts:(0.0,tuple(acts)),
        distance_fn=lambda a,b:abs(a-b),tied_fn=lambda a,b:a==b,
    )
    assert out['action'] is None and out['native_choice_claim'] is False
    assert set(out['missing_consequence_actions'])=={'clarify','ask','remain-silent'}


@pytest.mark.parametrize('target',['ask','clarify'])
def test_multiple_unforced_answer_set_changes_response_only_after_native_act_choice(tmp_path,target):
    n=Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/f'{target}.sqlite3'),terra_enabled=False)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-owner-test',content='What is Mira?',
        metadata={'owner_authenticated':True})
    n.state.last_event_id=event.id
    n.state.conversational_turn=1
    n.state.math_kernel.reasoning=multi_answer_reasoning()
    thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,
        statement='Mira is scholar. Mira is teacher.',
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
    structure=analyze_dialogue_structure(event.content)

    # Multiplicity alone cannot choose/suppress the existing ordinary response.
    audit=n._resolution_speech_act_selection(
        thought,SimpleNamespace(state=n.state.math_kernel),event=event,current_structure=structure)
    assert audit['native_choice_claim'] is False
    assert audit['changes_response_content'] is False
    assert audit['content_formation']['ordinary_answer_preserved'] is True
    assert n._hf2_resolution_observation is None

    seed_speech_geometry(n,target=target)
    audit=n._resolution_speech_act_selection(
        thought,SimpleNamespace(state=n.state.math_kernel),event=event,current_structure=structure)
    assert audit['action']==target and audit['native_choice_claim'] is True
    assert audit['decision_layer']=='learned-deliberative'
    assert audit['changes_response_content'] is True
    assert audit['content_formation']['ordinary_answer_present'] is True
    assert audit['content_formation']['ordinary_answer_preserved'] is False
    assert audit['content_formation']['alternative_inventory_choice_authority'] is False
    obs=n._hf2_resolution_observation
    assert obs is not None
    units=obs['thought'].resolution_content
    assert any(u.kind=='proposition-alternatives' for u in units)
    assert all(u.act==target and u.speech_act_selection_authority is False for u in units)


def test_unique_supported_answer_is_not_displaced_by_unrelated_proof_multiplicity(tmp_path):
    n=Noeron(MockLanguageEngine(),LocalEventStore(tmp_path/'unique.sqlite3'),terra_enabled=False)
    event=CognitiveEvent(kind=EventKind.USER_MESSAGE,source='isolated-owner-test',content='What is Mira?',
        metadata={'owner_authenticated':True})
    n.state.last_event_id=event.id;n.state.conversational_turn=1
    r=MultiMemoryReasoningMathState(
        logical_query=LogicalQuery(kind='relation-from-subject',raw='What is Mira?'),
        answer_candidates=[LogicalProposition(subject='mira',relation='is',object='scholar')],
        answer_selection_status='unique-proof-supported-answer',proof_gate_status='proof-support-gate-passed',
        inference_steps=[
            InferenceStep(rule='r1',premises=['a::true::true'],conclusion='x::true::true'),
            InferenceStep(rule='r2',premises=['b::true::true'],conclusion='x::true::true'),
        ],
    )
    n.state.math_kernel.reasoning=r
    thought=cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE,statement='Mira is scholar.',
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
    seed_speech_geometry(n,target='ask')
    audit=n._resolution_speech_act_selection(
        thought,SimpleNamespace(state=n.state.math_kernel),event=event,
        current_structure=analyze_dialogue_structure(event.content))
    assert audit['requires_resolution'] is False
    assert audit['native_choice_claim'] is False
    assert audit['changes_response_content'] is False
    assert audit['content_formation']['ordinary_answer_preserved'] is True
    assert 'proof-alternatives' in audit['content_formation']['alternative_inventory_kinds']
    assert audit['content_formation']['alternative_inventory_changes_eligibility'] is False
