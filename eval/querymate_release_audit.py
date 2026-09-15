"""Offline release evidence and explicitly enumerated, backed-up cleanup only."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from eval.scoring import compare, write_json

ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT.parent/'agentic-data-analyst-backups/querymate-pre-release-20260915-143123'
INVENTORY=ROOT/'docs/QUERYMATE_FILE_INVENTORY.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offline():
    freeze=read(ROOT/'eval/final_mixed_freeze.json')
    changes=[]
    for name,h in freeze['hashes'].items():
        if sha(ROOT/name)!=h:
            changes.append(name)
    assert set(changes)<= {'ui/app.py'}, 'Frozen behavior or evaluation artifact changed'
    cases=read(ROOT/'eval/final_mixed_cases.json')
    saved={r['id']:r for r in read(ROOT/'eval/final_mixed_per_case.json')}
    events={}
    starts=Counter()
    for line in (ROOT/'eval/final_mixed_events.jsonl').read_text().splitlines():
        row=json.loads(line); key=(row['id'],row['stage'])
        if row['state']=='started':
            starts[key]+=1
        else:
            assert key not in events
            events[key]=row
    assert len(cases)==len(saved)==len({c['id'] for c in cases})==200
    assert Counter(c['kind'] for c in cases)=={'clear':140,'time':20,'metric':20,'entity_filter':20}
    assert len(events)==429 and set(events)==set(starts) and all(n==1 for n in starts.values())
    correct=Counter()
    for c in cases:
        for mode in ('off','on'):
            event=events.get((c['id'],'followup')) if mode=='on' else None
            p=(event or events[(c['id'],mode)])['payload']
            matched=p.get('status')=='success' and compare(c['ground_truth_result'],p.get('result',[]),c['ordered'])
            assert bool(matched)==saved[c['id']][mode+'_correct'], 'Stored scoring disagrees with frozen comparator'
            correct[mode]+=bool(matched)
            correct[mode+'_'+c['kind']]+=bool(matched)
    assert correct['off']==138 and correct['on']==147 and correct['on_clear']==125
    evidence={'mode':'OFFLINE ONLY; zero Qwen calls; no benchmark rerun',
        'counts':dict(correct),'distribution':dict(Counter(c['kind'] for c in cases)),
        'off_accuracy':69.0,'on_accuracy':73.5,'delta_pp':4.5,'on_clear_accuracy':125/140*100,
        'unique_completed_stages':len(events),'frozen_non_ui_hashes_unchanged':True,
        'allowed_wiring_change':changes,'ui_sha256':sha(ROOT/'ui/app.py'),
        'source_hashes':{name:sha(ROOT/name) for name in ['eval/final_mixed_cases.json','eval/final_mixed_events.jsonl','eval/scoring.py']}}
    write_json(ROOT/'eval/querymate_offline_verification.json',evidence)
    print(json.dumps(evidence,ensure_ascii=False))


def inventory():
    assert not INVENTORY.exists(), 'Preserve prior inventory'
    backup=read(BACKUP/'manifest.json')
    members={r['path']:r for r in backup['files']}
    archive=BACKUP/'worktree-with-uncommitted-evidence.tar.gz'
    assert sha(archive)==backup['archive_sha256']
    names=set(subprocess.check_output(['/usr/bin/git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0'))-{''}
    for parent in (ROOT/'app',ROOT/'ui',ROOT/'eval',ROOT/'scripts',ROOT/'tests',ROOT/'.pytest_cache',ROOT):
        if parent==ROOT:
            candidates=list(parent.glob('*.pyc'))+list(parent.glob('.DS_Store'))
        else:
            candidates=list(parent.rglob('*')) if parent.exists() else []
        for p in candidates:
            if p.is_file() and not p.is_symlink() and (p.suffix=='.pyc' or p.name=='.DS_Store' or '.pytest_cache' in p.parts):
                names.add(str(p.relative_to(ROOT)))
    texts={n:(ROOT/n).read_text(errors='replace') for n in names
           if (ROOT/n).is_file() and Path(n).suffix in ('.py','.md','.sh','.yml','.toml')
           and not n.startswith('eval/final_mixed_authoring/')}
    frozen=set()
    for p in (ROOT/'eval').glob('*freeze*.json'):
        value=read(p)
        if isinstance(value,dict): frozen.update(value.get('hashes',{}))
    records=[]
    for name in sorted(names):
        p=ROOT/name
        if not p.is_file() or p.is_symlink(): continue
        references=[n for n,text in texts.items() if n!=name and name in text]
        production=(name.startswith(('app/','ui/','scripts/','data/')) or name in {
            'eval/strong_baseline.py','eval/strong_baseline_v2.py','requirements.txt','docker-compose.yml','.env.example','LICENSE','ATTRIBUTION.md','.gitignore','pytest.ini'})
        temporary=p.suffix=='.pyc' or p.name=='.DS_Store' or '.pytest_cache' in p.parts
        rejected=name.startswith('eval/final_mixed_authoring/')
        group='D' if temporary else 'A' if production else 'B' if name.startswith(('eval/','tests/')) or name in {
            'FINAL_MIXED_CLARIFICATION_EVALUATION.md','FINAL_300_CLARIFICATION_REGRESSION.md','CLARIFICATION_METRIC_AUDIT.md'} else 'C'
        action='delete_regenerable_cache' if temporary else 'archive_remove' if rejected else 'keep'
        if rejected:
            group='C'
            assert name in members and sha(p)==members[name]['sha256']
            assert name not in frozen and not references
        reason=('Regenerable cache; no unique code or evaluation record' if temporary else
                'Rejected initial authoring attempt; current authoring tool uses revision_1, no source/document/frozen-path dependency; raw evidence retained in verified external archive and commit 0bb12e4' if rejected else
                'Runtime/configuration/initialization dependency; baseline-named engine modules are actively imported' if production else
                'Evaluation, audit or test evidence retained at its existing path' if group=='B' else
                'Historical/project documentation or legacy source retained; navigation-only archival')
        records.append({'path':name,'class':group,'action':action,'reason':reason,'references':references,
            'frozen_path_reference':name in frozen,'sha256':sha(p),'size':p.stat().st_size,
            'backup':str(archive)+'::'+name if name in members else ('not needed: regenerable cache' if temporary else 'new release artifact; will be committed locally')})
    value={'backup_manifest':str(BACKUP/'manifest.json'),'backup_archive_sha256':backup['archive_sha256'],
        'dependency_check':'Production imports app.agent.scoped_clarification -> eval.strong_baseline_v2 -> eval.strong_baseline; both engine files retained. Every app module and all existing tests retained.',
        'excluded_from_cleanup':['.env','.env.*','.venv','.git','logs','.run','all Docker resources'],
        'records':records,'class_counts':dict(Counter(r['class'] for r in records)),
        'action_counts':dict(Counter(r['action'] for r in records))}
    write_json(INVENTORY,value)
    print(json.dumps({k:v for k,v in value.items() if k.endswith('_counts')},ensure_ascii=False))


def cleanup():
    value=read(INVENTORY)
    receipt=ROOT/'docs/QUERYMATE_CLEANUP_RECEIPT.json'
    assert not receipt.exists()
    selected=[r for r in value['records'] if r['action']!='keep']
    assert all(not r['path'].endswith('.lock') for r in selected)
    open_files=subprocess.run(['lsof','-F','n','--',*[str(ROOT/r['path']) for r in selected]],capture_output=True,text=True)
    assert open_files.returncode in (0,1)
    held={line[1:] for line in open_files.stdout.splitlines() if line.startswith('n')}
    assert not held, 'A cleanup candidate is held by a process; no files removed'
    archive=BACKUP/'worktree-with-uncommitted-evidence.tar.gz'
    assert sha(archive)==value['backup_archive_sha256']
    with tarfile.open(archive,'r:gz') as tar:
        for r in selected:
            p=ROOT/r['path']
            assert p.is_file() and not p.is_symlink() and sha(p)==r['sha256']
            if r['action']=='archive_remove':
                assert hashlib.sha256(tar.extractfile(r['path']).read()).hexdigest()==r['sha256']
    archived=[r['path'] for r in selected if r['action']=='archive_remove']
    if archived:
        subprocess.run(['/usr/bin/git','rm','--',*archived],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    for r in selected:
        if r['action']=='delete_regenerable_cache': (ROOT/r['path']).unlink()
    write_json(receipt,{'inventory_sha256':sha(INVENTORY),'executed':selected,
        'archive_removed':len(archived),'cache_files_removed':len(selected)-len(archived),
        'note':'Only enumerated verified paths removed. Cache directories may repopulate during normal tests/runtime. No locks, environments, logs, database or unrelated resources touched.'})
    print(json.dumps({'archived':len(archived),'cache_files_removed':len(selected)-len(archived)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['offline','inventory','cleanup'])
    args=p.parse_args(); {'offline':offline,'inventory':inventory,'cleanup':cleanup}[args.action]()
