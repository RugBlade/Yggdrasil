"""Authoritative M4C3S exact-HF1 baseline / intent / independent replay gate."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile

REPO=Path(os.environ['GITHUB_WORKSPACE']).resolve()
TMP=Path(os.environ['RUNNER_TEMP'])
OUT=REPO/'evidence';OUT.mkdir(exist_ok=True)
BASELINE_COMMIT='6d9b0df915d1e9aaa629731978cf52749da18764'
INTENT=REPO/'patches/hf2/0023-hf2-direct-proof-provenance.intent.patch'
INTENT_SHA='3f92a0d90789de3b04013cb43cae25612000fe15c2f10bb0c684ff0afa125933'
INTENT_BYTES=49785
SCOPE={'src/noeron/direct_proof.py','src/noeron/inference.py','src/noeron/reasoning.py',
       'src/noeron/math/models.py','src/noeron/cognition/models.py','src/noeron/cognition/kernel.py',
       'src/noeron/conversation_proof.py','src/noeron/conversation_resolution.py'}
HELPERS=['conversation_premises.py','conversation_bridge.py','conversation_reasoning.py',
         'conversation_proof.py','conversation_runtime_gate.py','conversation_actions.py','conversation_resolution.py']
MILESTONES=list('abcdefghijklm')+list('opqr')

def run(args,*,cwd=REPO,env=None,log=None):
    print('RUN', ' '.join(map(str,args)),flush=True)
    if log:
        with (OUT/log).open('w') as handle:
            result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,stdout=handle,stderr=subprocess.STDOUT)
        lines=(OUT/log).read_text(errors='replace').splitlines()
        print('\n'.join(lines[-25:]),flush=True)
        result.check_returncode()
        return
    subprocess.run(list(map(str,args)),cwd=cwd,env=env,check=True)

def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'src/noeron').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}

def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2)+'\n')

def patches():
    result=[]
    for number in range(1,23):
        found=list((REPO/'patches/hf2').glob(f'{number:04d}-*.patch'))
        found=[p for p in found if not p.name.endswith('.intent.patch')]
        assert len(found)==1,(number,found)
        result.append(found[0])
    return result

CHAIN=patches()
save('m4c3s-published-chain-identities.json',[
    {'path':str(p.relative_to(REPO)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in CHAIN])

def reconstruct(label):
    root=TMP/('ygg-hf1-m4c3s-'+label)
    assert not root.exists(),root
    run([sys.executable,REPO/'scripts/verify_hf1_exact_fixture.py','--extract-dir',root,
         '--extract-all','--evidence',OUT/f'm4c3s-{label}-hf1-identity.json'])
    helper_ids=[]
    for name in HELPERS:
        src=REPO/'src/noeron'/name
        shutil.copyfile(src,root/'src/noeron'/name)
        helper_ids.append({'path':'src/noeron/'+name,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
    save(f'm4c3s-{label}-original-helper-identities.json',helper_ids)
    run(['git','init','-q'],cwd=root)
    run(['git','config','user.name','Yggdrasil HF2 CI'],cwd=root)
    run(['git','config','user.email','hf2-ci@example.invalid'],cwd=root)
    run(['git','add','.'],cwd=root);run(['git','commit','-qm','Exact HF1 plus ORIGINAL carrier helpers'],cwd=root)
    for patch in CHAIN:
        run(['git','apply','--check',patch],cwd=root);run(['git','apply',patch],cwd=root)
        run(['git','diff','--check'],cwd=root)
    run(['git','add','.'],cwd=root);run(['git','commit','-qm','Exact published post0022'],cwd=root)
    return root

def sealed_source():
    archive=TMP/'m4c3s-sealed-post0022.zip'
    with archive.open('wb') as output:
        subprocess.run(['gh','api','repos/RugBlade/Yggdrasil/actions/artifacts/10594550960/zip'],stdout=output,check=True)
    raw=archive.read_bytes()
    assert len(raw)==679959 and hashlib.sha256(raw).hexdigest()=='b4f45fe3db4af1a019443cae1c563f9e3c371bad04708277fed8e0b1ed6207e0'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:source=z.read('m4c3r-exact-post0022-published-source.tar.gz')
    assert len(source)==663382 and hashlib.sha256(source).hexdigest()=='2d48868a39883be1a19399dc55f9735806b8cfa050d4136757be0d5fed3c05bd'
    with tarfile.open(fileobj=io.BytesIO(source)) as t:
        return {p.name:hashlib.sha256(t.extractfile(p).read()).hexdigest() for p in t.getmembers() if p.isfile()}

def suite(carrier,include_candidate):
    files=sorted((carrier/'tests').glob('test_v082_hf2_*.py'))
    files += [carrier/f'tests/hf2_m4c3{x}' for x in MILESTONES]
    if include_candidate:files.append(carrier/'tests/hf2_m4c3s')
    assert files and all(p.exists() for p in files)
    return files

def pytest(root,carrier,label,paths,expected):
    env=dict(os.environ,PYTHONPATH=str(root/'src'),NOERON_DB_PATH=str(TMP/f'm4c3s-{label}.sqlite3'))
    run([sys.executable,'-c',"import noeron.inference,pathlib; assert pathlib.Path(noeron.inference.__file__).is_relative_to(pathlib.Path("+repr(str(root/'src'))+"))"],cwd=carrier,env=env)
    xml=OUT/f'm4c3s-{label}.xml'
    run([sys.executable,'-m','pytest','-q',*paths,'--junitxml='+str(xml)],cwd=carrier,env=env,log=f'm4c3s-{label}.txt')
    cases=ET.parse(xml).getroot().findall('.//testcase')
    assert len(cases)==expected and all(c.find(tag) is None for c in cases for tag in ('failure','error','skipped')),(label,len(cases),expected)
    return {'passed':len(cases),'failed':0,'skipped':0}

def apply_candidate(root,label,expected_source):
    raw=INTENT.read_bytes()
    assert len(raw)==INTENT_BYTES and hashlib.sha256(raw).hexdigest()==INTENT_SHA
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()=='82af12392377de6cbc7dd30297982aaa09d1f6ea'
    run(['git','apply','--check',INTENT],cwd=root);run(['git','apply',INTENT],cwd=root)
    run(['git','add','-N','src/noeron/direct_proof.py'],cwd=root);run(['git','diff','--check'],cwd=root)
    run([sys.executable,'-m','compileall','-q','src/noeron'],cwd=root)
    current=hashes(root)
    changed={name for name in set(current)|set(expected_source) if current.get(name)!=expected_source.get(name)}
    assert changed==SCOPE,changed
    save(f'm4c3s-{label}-source-hashes.json',current)
    save(f'm4c3s-{label}-scope.json',{'files':sorted(changed),'patch_sha256':INTENT_SHA,'patch_bytes':INTENT_BYTES})
    return current

fix=reconstruct('candidate')
expected=sealed_source();assert hashes(fix)==expected and len(expected)==58
save('m4c3s-post0022-sealed-source-parity.json',{'verified':True,'files':expected})
run([sys.executable,'-m','pip','install','--disable-pip-version-check','-e',str(fix)+'[dev]'],log='m4c3s-dependencies.txt')
baseline=TMP/'m4c3s-baseline-carrier';baseline.mkdir()
archive=TMP/'m4c3s-baseline-carrier.tar'
run(['git','archive','--format=tar','--output='+str(archive),BASELINE_COMMIT])
with tarfile.open(archive) as t:t.extractall(baseline,filter='data')
results={'baseline':pytest(fix,baseline,'baseline',suite(baseline,False),451)}
candidate_hashes=apply_candidate(fix,'candidate',expected)
results['focused']=pytest(fix,REPO,'focused',[REPO/'tests/hf2_m4c3s'],34)
results['complete']=pytest(fix,REPO,'complete',suite(REPO,True),485)
shutil.copyfile(INTENT,OUT/'0023-hf2-direct-proof-provenance.generated.patch')
replay=reconstruct('replay');assert hashes(replay)==expected
replay_hashes=apply_candidate(replay,'replay',expected)
assert replay_hashes==candidate_hashes
save('m4c3s-source-byte-parity.json',{'verified':True,'files':len(replay_hashes)})
results['replay_focused']=pytest(replay,REPO,'replay-focused',[REPO/'tests/hf2_m4c3s'],34)
results['replay_complete']=pytest(replay,REPO,'replay-complete',suite(REPO,True),485)
assert hashes(fix)==candidate_hashes and hashes(replay)==replay_hashes
source_archive=OUT/'m4c3s-exact-post0023-candidate-source.tar.gz'
with tarfile.open(source_archive,'w:gz') as t:
    for name in sorted(replay_hashes):t.add(replay/name,arcname=name)
run(['git','archive','--format=tar.gz','--output='+str(OUT/'m4c3s-carrier-evidence.tar.gz'),os.environ['GITHUB_SHA']])
design=json.loads((REPO/'docs/evidence/HF2_M4C3S_RUNTIME_COMPATIBILITY_20260920_MANIFEST.json').read_text())
save('HF2_M4C3S_CANDIDATE_RESULT.json',{'milestone':'M4C3S','status':'GREEN','run_id':os.environ['GITHUB_RUN_ID'],
    'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'source_commit':os.environ['GITHUB_SHA'],'baseline_commit':BASELINE_COMMIT,
    'patch_sha256':INTENT_SHA,'patch_bytes':INTENT_BYTES,'results':results,'source_byte_parity':True,
    'source_archive_sha256':hashlib.sha256(source_archive.read_bytes()).hexdigest(),'scope':sorted(SCOPE),
    'authority':design['authority'],'ordinary_0023_published':False,'m4c3s_sealed':False,'stage8b_complete':False})
save('m4c3s-evidence-sha256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.is_file()})
print('M4C3S CANDIDATE ALL GATES GREEN — PUBLICATION STILL SEPARATE',flush=True)
