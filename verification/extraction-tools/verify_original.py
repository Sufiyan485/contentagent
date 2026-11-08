from pathlib import Path
import json, os, hashlib, subprocess, time, difflib, re
D=Path(__file__).resolve().parent
S=Path(r'D:\Projects\AI_Social_Media')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','--no-optional-locks',*args],cwd=S,text=True).strip()
reviewed=json.loads((D/'verification/reviewed-source-baseline.json').read_text(encoding='utf-8-sig'))
full=json.loads((D/'verification/original-full-baseline.json').read_text())
print('Comparing original tracked and extended file hashes...',flush=True)
tracked=[]
for row in reviewed['Files']:
 p=S/row['Path']
 if not p.is_file() or sha(p).lower()!=row['SHA256'].lower():tracked.append(row['Path'])
current={};errors=[]
for root,dirs,names in os.walk(S,followlinks=False):
 dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink() and not (Path(root)/d).is_junction()]
 for name in names:
  p=Path(root)/name
  if p.is_symlink():continue
  try:current[p.relative_to(S).as_posix()]=sha(p)
  except OSError as e:errors.append({'path':p.relative_to(S).as_posix(),'error':type(e).__name__})
old=full['files']
report={'checked_at':time.time(),'initial_reviewed_head':reviewed['GitHead'],'final_head':git('rev-parse','HEAD'),'initial_reviewed_status':reviewed['GitStatus'],'final_status':git('status','--porcelain=v1','--untracked-files=all').splitlines(),'reviewed_tracked_count':len(reviewed['Files']),'tracked_mismatches':tracked,'extended_baseline_count':len(old),'extended_final_count':len(current),'extended_added':sorted(current.keys()-old.keys()),'extended_removed':sorted(old.keys()-current.keys()),'extended_changed':sorted(k for k in old.keys()&current.keys() if old[k]!=current[k]),'read_errors':errors,'scope':'Regular files found by non-link-following traversal, including ignored runtime/dependency/Git files. Symlink/junction target trees are not followed. Baselines are sequential scans, not atomic filesystem snapshots.'}
(D/'verification/original-integrity-result.json').write_text(json.dumps(report,indent=2))
manifest=json.loads((D/'EXTRACTION_MANIFEST.json').read_text())
diff_folder=D/'verification/adaptations';diff_folder.mkdir(exist_ok=True)
for row in manifest:
 p=D/row['destination'];row['destination_sha256']=sha(p);row['copied_unchanged']=row['destination_sha256']==row['source_sha256']
 if not row['copied_unchanged']:
  a=(S/row['source']).read_text(encoding='utf-8').splitlines(keepends=True);b=p.read_text(encoding='utf-8').splitlines(keepends=True)
  diff=''.join(difflib.unified_diff(a,b,fromfile='original/'+row['source'],tofile='standalone/'+row['destination']))
  filename=row['destination'].replace('/','__')+'.diff';(diff_folder/filename).write_text(diff,encoding='utf-8');row['adaptation_diff']='verification/adaptations/'+filename
(D/'EXTRACTION_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
core=['backend/app/agents/content.py','backend/app/agents/revision.py','backend/app/workflow.py','backend/app/services/artwork.py','backend/app/services/quality.py','backend/app/services/providers.py','backend/app/services/assets.py']
assert all(next(r for r in manifest if r['source']==name)['copied_unchanged'] for name in core)
# Secret-pattern scan of recipient-owned code/config/docs (synthetic test keys are not live credentials).
patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'(?<![A-Za-z0-9])(?:sk-proj-|sk-or-v1-|gsk_)[A-Za-z0-9_-]{20,}',r'AIza[A-Za-z0-9_-]{30,}',r'EAA[A-Za-z0-9]{60,}']
findings=[];absolute_runtime=[]
for folder in ['backend','assets','examples']:
 for p in (D/folder).rglob('*'):
  if p.suffix in ('.py','.css','.json','.txt') and p.is_file():
   text=p.read_text(encoding='utf-8')
   if any(re.search(pattern,text) for pattern in patterns):findings.append(p.relative_to(D).as_posix())
   if folder=='backend' and r'D:\Projects\AI_Social_Media' in text and 'tests' not in p.parts:absolute_runtime.append(p.relative_to(D).as_posix())
security={'pattern_scan_findings':findings,'original_absolute_runtime_paths':absolute_runtime,'original_env_copied':(D/'.env').exists(),'original_git_copied':(D/'.git').exists(),'note':'Heuristic secret scan plus allowlist provenance; no original environment file or credential-bearing runtime data was copied. Test-only credential literals are synthetic.'}
(D/'verification/security-scan.json').write_text(json.dumps(security,indent=2))
assert not findings and not absolute_runtime and not security['original_env_copied'] and not security['original_git_copied']
print(json.dumps({k:v for k,v in report.items() if k not in ('scope',)},indent=2),flush=True)
print('Unchanged core logic and secret-pattern scan passed.',flush=True)
