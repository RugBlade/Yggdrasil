"""Separate fresh exact-HF1 ordinary0001-0023 published-chain gate."""
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

REPO = Path(os.environ['GITHUB_WORKSPACE']).resolve()
TMP = Path(os.environ['RUNNER_TEMP'])
OUT = REPO / 'evidence'
OUT.mkdir(exist_ok=True)
FIX = TMP / 'ygg-hf1-m4c3s-published'
INTENT = REPO / 'patches/hf2/0023-hf2-direct-proof-provenance.intent.patch'
PUBLISHED = REPO / 'patches/hf2/0023-hf2-direct-proof-provenance.patch'
PATCH_SHA = '3f92a0d90789de3b04013cb43cae25612000fe15c2f10bb0c684ff0afa125933'
PATCH_BLOB = '82af12392377de6cbc7dd30297982aaa09d1f6ea'
HELPERS = ['conversation_premises.py', 'conversation_bridge.py', 'conversation_reasoning.py',
           'conversation_proof.py', 'conversation_runtime_gate.py', 'conversation_actions.py',
           'conversation_resolution.py']

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(raw):
    return dict(bytes=len(raw), sha256=sha(raw), git_blob=hashlib.sha1(
        b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())

def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n')

def run(args, *, cwd=REPO, env=None, log=None):
    print('RUN', ' '.join(map(str, args)), flush=True)
    if log:
        with (OUT / log).open('w') as handle:
            result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                                    stdout=handle, stderr=subprocess.STDOUT)
        print('\n'.join((OUT / log).read_text(errors='replace').splitlines()[-25:]), flush=True)
        result.check_returncode()
    else:
        subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)

def hashes(root):
    return {str(p.relative_to(root)): sha(p.read_bytes())
            for p in sorted((root / 'src/noeron').rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}

# Candidate artifact is an immutable comparison oracle, never the reconstruction tree.
archive = TMP / 'm4c3s-inspected-green-candidate.zip'
with archive.open('wb') as output:
    subprocess.run(['gh', 'api', 'repos/RugBlade/Yggdrasil/actions/artifacts/10637099937/zip'],
                   stdout=output, check=True)
raw = archive.read_bytes()
assert len(raw) == 2878507 and sha(raw) == 'dd1dfafe18976bd35b771d0b14ce10a02510ae72718bf62300947993e8bdbe98'
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    evidence_hashes = json.loads(z.read('m4c3s-evidence-sha256.json'))
    for name, digest in evidence_hashes.items():
        assert sha(z.read(name)) == digest, name
    green = json.loads(z.read('HF2_M4C3S_CANDIDATE_RESULT.json'))
    expected = json.loads(z.read('m4c3s-candidate-source-hashes.json'))
    expected_helpers = json.loads(z.read('m4c3s-candidate-original-helper-identities.json'))
    expected_chain = json.loads(z.read('m4c3s-published-chain-identities.json'))
    expected_base = json.loads(z.read('m4c3s-post0022-sealed-source-parity.json'))['files']
    assert z.read('0023-hf2-direct-proof-provenance.generated.patch') == PUBLISHED.read_bytes()
assert green['status'] == 'GREEN' and green['run_id'] == '35597333634'
assert green['source_commit'] == '752ed6c32229f2d7efe5f09f5566636dff744fc0'
assert len(expected) == 59 and len(expected_base) == 58 and len(expected_helpers) == 7
patch_raw = PUBLISHED.read_bytes()
assert patch_raw == INTENT.read_bytes()
assert identity(patch_raw) == dict(bytes=49785, sha256=PATCH_SHA, git_blob=PATCH_BLOB)
save('m4c3s-published-0023-identity.json', dict(identity(patch_raw), intent_published_raw_equality=True,
     candidate_artifact_id=10637099937, candidate_run_id=35597333634))
for name, expected_identity in green['test_contract'].items():
    assert identity((REPO / name).read_bytes()) == expected_identity, name
save('m4c3s-published-test-identities.json', green['test_contract'])

chain = []
for number in range(1, 24):
    found = [p for p in (REPO / 'patches/hf2').glob(f'{number:04d}-*.patch')
             if not p.name.endswith('.intent.patch')]
    assert len(found) == 1, (number, found)
    patch = found[0]
    record = dict(path=str(patch.relative_to(REPO)), bytes=patch.stat().st_size, sha256=sha(patch.read_bytes()))
    if number <= 22:
        assert record == expected_chain[number - 1], record
    chain.append(patch)
save('m4c3s-published-chain-identities.json', [dict(path=str(p.relative_to(REPO)), **identity(p.read_bytes())) for p in chain])

assert not FIX.exists(), FIX
run([sys.executable, REPO / 'scripts/verify_hf1_exact_fixture.py', '--extract-dir', FIX,
     '--extract-all', '--evidence', OUT / 'm4c3s-published-hf1-identity.json'])
actual_helpers = []
for name in HELPERS:
    src = REPO / 'src/noeron' / name
    shutil.copyfile(src, FIX / 'src/noeron' / name)
    actual_helpers.append(dict(path='src/noeron/' + name, sha256=sha(src.read_bytes())))
assert actual_helpers == expected_helpers
save('m4c3s-published-original-helper-identities.json', actual_helpers)
run(['git', 'init', '-q'], cwd=FIX)
run(['git', 'config', 'user.name', 'Yggdrasil HF2 CI'], cwd=FIX)
run(['git', 'config', 'user.email', 'hf2-ci@example.invalid'], cwd=FIX)
run(['git', 'add', '.'], cwd=FIX)
run(['git', 'commit', '-qm', 'Exact HF1 plus ORIGINAL helpers'], cwd=FIX)
for number, patch in enumerate(chain, 1):
    run(['git', 'apply', '--check', patch], cwd=FIX)
    run(['git', 'apply', patch], cwd=FIX)
    run(['git', 'diff', '--check'], cwd=FIX)
    if number == 22:
        assert hashes(FIX) == expected_base
        save('m4c3s-published-post0022-parity.json', dict(verified=True, files=58))
assert hashes(FIX) == expected
save('m4c3s-published-source-hashes.json', expected)
save('m4c3s-published-candidate-source-parity.json', dict(verified=True, files=59, candidate_run=35597333634))
run([sys.executable, '-m', 'compileall', '-q', 'src/noeron'], cwd=FIX)
run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-e', str(FIX) + '[dev]'],
    log='m4c3s-published-dependencies.txt')
env = dict(os.environ, PYTHONPATH=str(FIX / 'src'), NOERON_DB_PATH=str(TMP / 'm4c3s-published-test-only.sqlite3'))
run([sys.executable, '-c', 'import noeron.inference,pathlib; assert pathlib.Path(noeron.inference.__file__).is_relative_to(pathlib.Path(' + repr(str(FIX / 'src')) + '))'], env=env)
paths = sorted((REPO / 'tests').glob('test_v082_hf2_*.py'))
paths += [REPO / f'tests/hf2_m4c3{x}' for x in list('abcdefghijklm') + list('opqrs')]
assert all(p.exists() for p in paths)
run([sys.executable, '-m', 'pytest', '-q', *paths, '--junitxml=' + str(OUT / 'm4c3s-published-complete.xml')],
    env=env, log='m4c3s-published-complete.txt')
cases = ET.parse(OUT / 'm4c3s-published-complete.xml').getroot().findall('.//testcase')
assert len(cases) == 485 and all(c.find(tag) is None for c in cases for tag in ('failure', 'error', 'skipped'))
assert hashes(FIX) == expected
source = OUT / 'm4c3s-exact-post0023-published-source.tar.gz'
with tarfile.open(source, 'w:gz') as t:
    for name in sorted(expected):
        t.add(FIX / name, arcname=name)
save('HF2_M4C3S_PUBLISHED_CHAIN_RESULT.json', dict(status='GREEN', milestone='M4C3S-published-chain',
     run_id=os.environ['GITHUB_RUN_ID'], source_commit=os.environ['GITHUB_SHA'],
     run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], candidate_run=35597333634,
     patch_chain=list(range(1,24)), patch_identity=identity(patch_raw),
     intent_published_raw_equality=True, source_byte_parity=True, source_files=59,
     source_archive=identity(source.read_bytes()), results=dict(passed=485, failed=0, skipped=0),
     authority=green['authority'], ordinary_0023_published=True, m4c3s_sealed=False, stage8b_complete=False))
save('m4c3s-published-evidence-sha256.json', {p.name: sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file()})
print('M4C3S SEPARATE PUBLISHED CHAIN GREEN - INSPECTION AND MIRRORS REQUIRED BEFORE SEAL', flush=True)
