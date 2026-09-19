"""M4C3R: surface correspondence only; full typed inventory remains auditable."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from noeron.cognition import models as cm
from noeron.conversation_resolution import (
    build_operator_resolution_calibration, native_current_turn_alternative_sources,
    resolution_content_units,
)
from noeron.development import NativeLanguageFaculty
from noeron.english_egress import realize_native_thought
from noeron.language_dialogue import analyze_dialogue_structure, referent_mentions
from noeron.llm import MockLanguageEngine
from noeron.math import dkt
from noeron.math.models import (
    InferenceStep, LogicalProposition, LogicalQuery, MultiMemoryReasoningMathState,
)
from noeron.memory import LocalEventStore
from noeron.models import CognitiveEvent, EventKind
from noeron.orchestrator import Noeron


def rows(text='Did she leave?'):
    return native_current_turn_alternative_sources(analyze_dialogue_structure(text,
        recent_referents=referent_mentions(analyze_dialogue_structure('Mira met Sara.'))))


def realize(candidates=(), *, action='clarify', units=None, event_id=None, statement=''):
    event_id = event_id or uuid4()
    if units is None:
        units = resolution_content_units(candidates, action=action, source_event_id=event_id)
    thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement=statement,
        resolution_content=units,
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event_id))
    before = thought.model_dump_json()
    utterance = NativeLanguageFaculty().realize(thought, cm.LanguageFacultyState())
    assert thought.model_dump_json() == before
    for unit in thought.resolution_content:
        assert unit.unresolved is True
        assert all(v is False for k, v in unit.model_dump().items() if k.endswith('_authority'))
    return utterance, thought


def test_reference_duplicate_surfaces_once_with_full_typed_inventory_and_english():
    candidates = rows()
    assert [x.kind for x in candidates] == ['reference-alternatives', 'qud-alternatives']
    assert candidates[1].source_units[1] == 'unresolved-source:' + candidates[0].source_id
    u, thought = realize(candidates)
    assert u.native_text == 'she: sara / mira?'
    assert u.utterance_plan == ['she: sara / mira?']
    assert u.grammar_frames == ['native-resolution-reference-alternatives']
    assert len(thought.resolution_content) == 2
    assert all(tuple(x.alternatives) == ('sara', 'mira') for x in thought.resolution_content)
    english, audit = realize_native_thought(thought, u)
    assert english == 'She: sara / mira?'
    assert all(v is False for k, v in audit.items() if k.endswith('_authority'))


def test_event_role_derivatives_surface_only_the_two_independent_primaries():
    candidates = rows('Did Mira give Omar the book?')
    u, thought = realize(candidates)
    assert len(thought.resolution_content) == 4
    assert u.utterance_plan == ['give omar: recipient / theme?', 'book: theme / patient?']
    assert u.grammar_frames == ['native-resolution-event-role-alternatives'] * 2
    assert len({x.source_id for x in candidates[:2]}) == 2


@pytest.mark.parametrize('reverse_inventory', [False, True])
def test_surface_correspondence_is_independent_of_inventory_order(reverse_inventory):
    candidates = rows()
    if reverse_inventory:
        candidates = tuple(reversed(candidates))
    u, _ = realize(candidates)
    assert u.native_text == 'she: sara / mira?'


def test_set_equivalent_wrapper_keeps_primary_order_without_ranking():
    primary, q = rows()
    q = replace(q, alternatives=('mira', 'sara'),
        source_units=(*q.source_units[:2], 'candidate:mira', 'candidate:sara'))
    u, thought = realize((primary, q))
    assert u.native_text == 'she: sara / mira?'
    assert [x.alternatives for x in thought.resolution_content] == [['sara', 'mira'], ['mira', 'sara']]


def test_two_independent_reference_sources_with_identical_wording_do_not_collapse():
    candidates = rows('Did she leave? Did she stay?')
    primary = [x for x in candidates if x.kind == 'reference-alternatives']
    assert len(primary) == 2 and primary[0].source_id != primary[1].source_id
    assert primary[0].focus_surface == primary[1].focus_surface == 'she'
    u, thought = realize(candidates)
    assert u.utterance_plan == ['she: sara / mira?', 'she: sara / mira?']
    assert len(thought.resolution_content) == 4


def test_independent_event_role_sources_with_identical_options_do_not_collapse():
    primary = rows('Did Mira give Omar the book?')[0]
    other = replace(primary, source_id='event-role-independent',
        source_units=('event:1:0', *primary.source_units[1:]))
    u, _ = realize((primary, other))
    assert u.utterance_plan == ['give omar: recipient / theme?'] * 2


@pytest.mark.parametrize('action', ['ask', 'clarify'])
def test_qud_with_absent_primary_remains_surface_content(action):
    u, thought = realize((rows()[1],), action=action)
    assert u.native_text == 'Did she leave?: sara / mira?'
    assert len(thought.resolution_content) == 1


@pytest.mark.parametrize('case', [
    'no-link', 'wrong-link', 'extra-link', 'no-qud', 'extra-qud', 'unknown-provenance',
    'missing-candidate', 'extra-candidate', 'different-source-id', 'different-alternatives',
    'empty-qud-id', 'empty-source-id', 'existing-question',
])
def test_unproved_or_independent_qud_correspondence_remains_visible(case):
    primary, q = rows()
    sources = list(q.source_units)
    if case == 'no-link': sources.pop(1)
    elif case == 'wrong-link': sources[1] = 'unresolved-source:independent'
    elif case == 'extra-link': sources.append('unresolved-source:independent')
    elif case == 'no-qud': sources.pop(0)
    elif case == 'extra-qud': sources.append('qud:independent')
    elif case == 'unknown-provenance': sources.append('independent-source:additional')
    elif case == 'missing-candidate': sources.pop()
    elif case == 'extra-candidate': sources.append('candidate:omar')
    elif case == 'different-source-id': q = replace(q, source_id='independent-wrapper')
    elif case == 'different-alternatives':
        q = replace(q, alternatives=('sara', 'omar'))
        sources = [*sources[:2], 'candidate:sara', 'candidate:omar']
    elif case == 'empty-qud-id': sources[0] = 'qud:'
    elif case == 'empty-source-id': sources[1] = 'unresolved-source:'
    elif case == 'existing-question': q = replace(q, existing_question='Independent question?')
    q = replace(q, source_units=tuple(sources))
    u, _ = realize((primary, q))
    assert len(u.utterance_plan) == 2
    assert u.utterance_plan[1] == q.focus_surface + ': ' + ' / '.join(q.alternatives) + '?'


@pytest.mark.parametrize('case', ['wrong-event', 'wrong-act', 'duplicate-options', 'blank-option', 'single-option'])
def test_ineligible_or_different_act_primary_cannot_cover_current_qud(case):
    event_id = uuid4()
    units = resolution_content_units(rows(), action='clarify', source_event_id=event_id)
    change = {
        'wrong-event': {'source_event_id': uuid4()},
        'wrong-act': {'act': 'ask'},
        'duplicate-options': {'alternatives': ['sara', 'mira', 'sara']},
        'blank-option': {'alternatives': ['sara', '']},
        'single-option': {'alternatives': ['sara']},
    }[case]
    units[0] = units[0].model_copy(update=change)
    u, _ = realize(units=units, event_id=event_id)
    assert 'Did she leave?: sara / mira?' in u.utterance_plan


def test_conflicting_primary_source_id_is_not_guessed_away():
    primary, q = rows()
    other = replace(primary, alternatives=('mira', 'omar'))
    u, _ = realize((primary, other, q))
    assert len(u.utterance_plan) == 3


@pytest.mark.parametrize('kind', ['proposition-alternatives', 'proof-alternatives'])
def test_nonprimary_kind_never_covers_a_qud_even_with_matching_id_and_options(kind):
    primary, q = rows()
    u, _ = realize((replace(primary, kind=kind), q))
    assert len(u.utterance_plan) == 2


@pytest.mark.parametrize('action', ['ask', 'clarify'])
def test_proposition_and_proof_options_stay_exact_unranked_and_act_neutral(action):
    reasoning = MultiMemoryReasoningMathState(
        logical_query=LogicalQuery(kind='relation-from-subject', raw='What is Mira?'),
        answer_candidates=[LogicalProposition(subject='mira', relation='is', object=o)
                           for o in ('scholar', 'teacher')],
        answer_selection_status='multiple-proof-supported-answers-no-forced-choice',
        inference_steps=[InferenceStep(rule='r1', premises=['a::true::true'], conclusion='b::true::true'),
                         InferenceStep(rule='r2', premises=['c::true::true'], conclusion='b::true::true')])
    candidates = native_current_turn_alternative_sources(analyze_dialogue_structure('What is Mira?'), reasoning)
    assert [x.kind for x in candidates] == ['proposition-alternatives', 'proof-alternatives']
    u, thought = realize(candidates, action=action)
    assert len(u.utterance_plan) == 2
    for row, unit in zip(candidates, thought.resolution_content):
        assert tuple(unit.alternatives) == row.alternatives
        assert all(x in u.native_text for x in row.alternatives)


def test_existing_statement_is_not_overwritten_by_resolution_content():
    u, _ = realize(rows(), statement='Existing native statement.')
    assert u.native_text == 'Existing native statement.'


def seed_geometry(n, target=None, tied=False):
    # Explicitly synthetic consequence-state fixture, not live experience.
    context = n.state.math_kernel.dkt.core_knot
    st = n.state.cognition.speech_act_development
    for i, action in enumerate(('clarify', 'ask', 'defer', 'remain-silent'), 1):
        pre = context.model_copy(deep=True)
        if not tied and action != target:
            pre.c0[0] += i * .2
        pre.invariant_signature = dkt.invariant_signature(pre)
        st.action_pre_knots[action] = pre
        st.action_post_knots[action] = context.model_copy(deep=True)
        st.action_observations[action] = 1
    st.transition_observations = 4


@pytest.mark.parametrize('target', ['clarify', 'ask', 'tie', 'incomplete'])
def test_native_geometry_alone_selects_act_and_blank_geometry_remains_silent(tmp_path, target):
    def owner(text):
        return CognitiveEvent(kind=EventKind.USER_MESSAGE, source='isolated-owner-test',
            content=text, trusted=True, metadata={'owner_authenticated': True})
    n = Noeron(MockLanguageEngine(), LocalEventStore(tmp_path / 'isolated.sqlite3'), terra_enabled=False)
    n.ingest(owner('Mira met Sara.'))
    event = owner('Did she leave?')
    reply = n.ingest(event)
    assert reply.native_text == ''
    assert reply.speech_act_audit['native_choice_claim'] is False
    assert reply.speech_act_audit['action'] is None
    assert reply.speech_act_audit['selection_status'] == 'unresolved-insufficient-speech-act-consequence-geometry'
    thought = cm.NativeThought(kind=cm.NativeThoughtKind.RESPONSE, statement='',
        mathematical_provenance=cm.MathematicalProvenance(source_event_id=event.id))
    seed_geometry(n, target=target, tied=target == 'tie')
    if target == 'incomplete':
        del n.state.cognition.speech_act_development.action_pre_knots['ask']
    audit = n._resolution_speech_act_selection(thought, SimpleNamespace(state=n.state.math_kernel),
        event=event, current_structure=reply.language_interpretation['structure'])
    assert audit['content_formation']['alternative_inventory_choice_authority'] is False
    assert audit['changes_outward_transport'] is False
    if target in {'tie', 'incomplete'}:
        assert audit['action'] is None and audit['native_choice_claim'] is False
        assert n._hf2_resolution_observation is None
        return
    assert audit['action'] == target and audit['native_choice_claim'] is True
    assert audit['decision_layer'] == 'learned-deliberative'
    observed = n._hf2_resolution_observation['thought']
    assert observed.native_utterance.native_text == (
        'she: sara / mira?' if target == 'clarify' else 'Did she leave?: sara / mira?')
    assert len(observed.resolution_content) == (2 if target == 'clarify' else 1)
    assert all(u.speech_act_selection_authority is False for u in observed.resolution_content)


@pytest.mark.parametrize('action', ['ask', 'clarify'])
def test_owner_calibration_does_not_become_native_choice(action):
    structure = analyze_dialogue_structure('Did she leave?',
        recent_referents=referent_mentions(analyze_dialogue_structure('Mira met Sara.')))
    plan = build_operator_resolution_calibration(action=action, authenticated_owner=True,
        current_structure=structure, existing_question_candidates=['Existing native question?'])
    assert plan.executable
    assert plan.origin == 'operator-directed-calibration-not-native-choice'
    assert plan.authority['native_choice'] is False
    assert plan.authority['preference_label'] is False
    assert plan.authority['relationship'] is False
    assert not build_operator_resolution_calibration(action=action, authenticated_owner=False,
        current_structure=structure, existing_question_candidates=['Existing native question?']).executable
