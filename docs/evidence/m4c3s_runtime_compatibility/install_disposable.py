"""Install a reviewed experimental overlay into a DISPOSABLE source copy only.

Exact replacements fail closed. This is a design instrument, not 0023 intent.
"""
from pathlib import Path
import hashlib
import json
import shutil


def install(root, instruments):
    root, instruments = Path(root), Path(instruments)
    changes = {}
    def edit(path, edits):
        p = root/'src/noeron'/path
        before = p.read_text()
        after = before
        for old,new in edits:
            assert after.count(old) == 1, (path,old[:120],after.count(old))
            after = after.replace(old,new)
        p.write_text(after)
        changes[path] = {'before': hashlib.sha256(before.encode()).hexdigest(),
                         'after': hashlib.sha256(after.encode()).hexdigest()}
    def class_edit(path, cls, edits):
        p=root/'src/noeron'/path
        text=p.read_text(); start=text.index('class '+cls+'(')
        end=text.find('\nclass ',start+1)
        if end<0: end=len(text)
        block=text[start:end]; new=block
        for old,repl in edits:
            assert new.count(old)==1,(path,cls,old)
            new=new.replace(old,repl)
        edit(path,[(block,new)])

    # Preserve the original instrument and its exact formal rule/budget contract.
    v1=(instruments/'two_ledger_v1.py').read_text()
    assert hashlib.sha256(v1.encode()).hexdigest()=='4462e4878de90a9ec4dd4a1f87d7de9451cf685fcf31e0d2d7c4586353c36f6e'
    v2=v1.replace('max_proof_records=1024):','max_proof_records=1024, admission_complete=False):')
    v2=v2.replace("if 'correction' in p.modifiers:","if 'correction' in p.modifiers and not admission_complete:")
    # Assemble the tested future module boundary in the disposable source copy.
    # Remove standalone prototype-only query/legacy projection helpers. The rule,
    # fingerprint, finite closure and proof enumeration functions remain exact.
    a=v2.index('@dataclass(frozen=True)\nclass NodeView:')
    b=v2.index('@dataclass(frozen=True)\nclass DirectRule:',a)
    v2=v2[:a]+v2[b:]
    a=v2.index('    def query(self, query):')
    b=v2.index('\ndef build_ledger(',a)
    v2=v2[:a]+v2[b:]
    adapter=(instruments/'runtime_adapter.py').read_text()
    adapter=adapter.replace('from __future__ import annotations\n','').replace('from two_ledger_v2 import build_ledger, canonical, digest\n','')
    (root/'src/noeron/direct_proof.py').write_text(v2+'\n\n'+adapter)

    class_edit('math/models.py','LogicalProposition',[
        ('confidence: float = 0.5','confidence: float | None = 0.5\n    proof_node_key: list = Field(default_factory=list)\n    proof_confidence: dict = Field(default_factory=dict)')])
    class_edit('math/models.py','InferenceStep',[
        ('confidence: float = 0.0','confidence: float | None = 0.0\n    proof_record: dict = Field(default_factory=dict)')])
    class_edit('math/models.py','MultiMemoryReasoningMathState',[
        ('confidence: float = 0.0','confidence: float | None = 0.0\n    confidence_evidence: dict = Field(default_factory=dict)\n    proof_ledger: dict = Field(default_factory=dict)\n    proof_ledger_complete: bool | None = None\n    proof_admission_audit: list[dict] = Field(default_factory=list)\n    autonomous_proof_candidates: list[LogicalProposition] = Field(default_factory=list)')])
    for cls in ('NativeProposition','NativeThought'):
        class_edit('cognition/models.py',cls,[('confidence: float = 0.5','confidence: float | None = 0.5\n    proof_evidence: dict = Field(default_factory=dict)')])

    edit('conversation_proof.py',[
        ('confidence: float = 1.0','confidence: float | None = None'),
        ('confidence = float(_field(raw, "confidence", 1.0) or 1.0)',
         'raw_confidence = _field(raw, "confidence", None)\n        confidence = None if raw_confidence is None else float(raw_confidence)')])
    edit('inference.py',[("def render_logical_proposition(p: LogicalProposition)",
        "_legacy_infer_for_disposable_comparison = infer\n\ndef infer(premises, query, *, max_steps=128, max_proof_records=1024, admission_mode='direct'):\n    from noeron.direct_proof import infer_compatible\n    return infer_compatible(premises, query, max_steps=max_steps, max_proof_records=max_proof_records, admission_mode=admission_mode)\n\n\ndef render_logical_proposition(p: LogicalProposition)")])
    p=root/'src/noeron/reasoning.py'; txt=p.read_text()
    old=txt[txt.index('    # Identical canonical propositions'):txt.index('    # Preserve all three proof-premise')]
    new="""    # Preserve parallel observations; established control admission is explicit.
    input_premises = bounded_premises + learned_premises + current_premises
    query = (logical_query or LogicalQuery()).model_copy(deep=True)
    inference_result = infer(input_premises, query, admission_mode='reasoning',
        max_steps=prototype_max_conclusion_steps, max_proof_records=prototype_max_proof_records)
    derived, inference_steps, raw_answers, selection_status = inference_result
    premises = [input_premises[i] for i in inference_result.admitted_indexes]

"""
    oldgate=txt[txt.index('    proof_gate=gate_inference_candidates('):txt.index('    answers=list(proof_gate.eligible_candidates)')]
    newgate="""    from noeron.direct_proof import gate_compatible, workspace_confidence
    all_bindings = list(zip(input_premises, proof_provenance, strict=True))
    bindings = [all_bindings[i] for i in inference_result.admitted_indexes]
    proof_gate = gate_compatible(inference_result, query, bindings, ambiguity_constraints)
    autonomous_gate = gate_compatible(inference_result, LogicalQuery(kind='derive-all'),
        bindings, ambiguity_constraints, candidates=derived)
"""
    oldconf=txt[txt.index('    # Proof confidence is constrained'):txt.index('    return MultiMemoryReasoningMathState(')]
    newconf="""    if not inference_result.ledger.proof_ledger_complete:
        open_questions, question_distances, question_status = [], {}, 'proof-gated-incomplete-ledger'
    confidence, confidence_evidence = workspace_confidence(
        inference_result, answers, query, confidence, bool(items))

"""
    edit('reasoning.py',[(old,new),(oldgate,newgate),(oldconf,newconf),
        ('    current_turn_index: int = 0,','    current_turn_index: int = 0,\n    prototype_max_conclusion_steps: int = 128,\n    prototype_max_proof_records: int = 1024,'),
        ('        premise_propositions=premises, derived_propositions=derived,',
         '        premise_propositions=premises, derived_propositions=derived,\n        confidence_evidence=confidence_evidence, proof_ledger=inference_result.ledger.to_dict(),\n        proof_ledger_complete=inference_result.ledger.proof_ledger_complete,\n        proof_admission_audit=inference_result.admission_audit,\n        autonomous_proof_candidates=list(autonomous_gate.eligible_candidates),')])
    edit('cognition/kernel.py',[
        ('if m.reasoning.native_inference_active:', 'if m.reasoning.native_inference_active or m.reasoning.proof_ledger_complete is False:'),
        ('novelty, clamp(confidence, 0.0, 1.0)','novelty, (None if confidence is None else clamp(confidence, 0.0, 1.0))'),
        ('def _proof_grounds(result: CausalMathResult, canonical: str)', 'def _proof_grounds(result: CausalMathResult, proposition)'),
        ('        for step in r.inference_steps:\n            if step.conclusion == canonical:',
         "        canonical = proposition.canonical()\n        from noeron.inference import proposition_key\n        for step in r.inference_steps:\n            matches = (tuple(step.proof_record['conclusion_key']) == proposition_key(proposition)) if step.proof_record else step.conclusion == canonical\n            if matches:"),
        ('        for a in m.reasoning.derived_propositions:',
         '        for a in (m.reasoning.autonomous_proof_candidates if m.reasoning.proof_ledger else m.reasoning.derived_propositions):')])
    # Identical call sites are deliberately all changed, count checked separately.
    p=root/'src/noeron/cognition/kernel.py'; txt=p.read_text()
    assert txt.count('self._proof_grounds(result,a.canonical())')==2
    assert txt.count('confidence=a.confidence,')==2
    edit('cognition/kernel.py',[(txt,txt.replace('self._proof_grounds(result,a.canonical())','self._proof_grounds(result,a)')
        .replace('confidence=a.confidence,','confidence=a.confidence, proof_evidence={"node_key": a.proof_node_key, "confidence": a.proof_confidence, "ledger_complete": m.reasoning.proof_ledger_complete},')
        .replace('causal_trace=m.causal_trace,','causal_trace=m.causal_trace,\n            proof_evidence={"ledger_complete": m.reasoning.proof_ledger_complete, "confidence": m.reasoning.confidence_evidence},'))])
    edit('conversation_resolution.py',[
        ('        canonicals = []\n        for row in answers:',
         "        canonicals = []\n        from noeron.inference import proposition_key\n        alias_keys = {}\n        for row in answers:\n            if hasattr(row, 'canonical'):\n                alias_keys.setdefault(row.canonical(), set()).add(proposition_key(row))\n        for row in answers:"),
        ('            if canonical and canonical not in canonicals:',
         "            if canonical and len(alias_keys.get(canonical, ())) > 1:\n                canonical = json.dumps({'canonical': canonical, 'proposition_key': list(proposition_key(row))}, sort_keys=True, separators=(',', ':'))\n            if canonical and canonical not in canonicals:"),
        ('            groups.setdefault(conclusion, []).append(payload)',
         "            record = _field(step, 'proof_record', {}) or {}\n            if record:\n                payload = json.dumps({'conclusion': conclusion, 'premises': premises, 'rule': rule,\n                    'record_id': record['record_id'], 'premise_keys': record['premise_keys'],\n                    'conclusion_key': record['conclusion_key'], 'rule_evidence_keys': record['rule_evidence_keys']},\n                    sort_keys=True, separators=(',', ':'))\n                conclusion = json.dumps(record['conclusion_key'], separators=(',', ':'))\n            groups.setdefault(conclusion, []).append(payload)")])
    # Record original vs final bytes, not intermediate edits of the same file.
    return changes
