from pathlib import Path
import ast, hashlib, json, shutil, subprocess, os, time
SRC=Path(r'D:\Projects\AI_Social_Media')
DST=Path(r'C:\Users\HP\OneDrive\Desktop\Content Agent')
assert DST.resolve()==DST and not DST.is_symlink() and not DST.is_junction()
def write(name, text):
 p=DST/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
# Hash all original regular files, including ignored dependencies/runtime/Git, without importing anything.
print('Capturing original file hashes...', flush=True)
files={}; errors=[]
for root, dirs, names in os.walk(SRC, followlinks=False):
 dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink() and not (Path(root)/d).is_junction()]
 for name in names:
  p=Path(root)/name
  if p.is_symlink(): continue
  try: files[p.relative_to(SRC).as_posix()]=sha(p)
  except OSError as e: errors.append({'path':p.relative_to(SRC).as_posix(),'error':type(e).__name__})
write('verification/original-full-baseline.json',json.dumps({'files':files,'errors':errors,'captured_at':time.time()},indent=2))
old=Path(r'C:\Users\HP\.codex\visualizations\2026\11\08\01a1ba42-79e0-7cc1-8be3-938612622667')
shutil.copyfile(old/'source-baseline.json',DST/'verification/reviewed-source-baseline.json')
shutil.copyfile(old/'content-agent-extraction-plan.md',DST/'EXTRACTION_PLAN.md')
print(f'Hashed {len(files)} original files; read errors {len(errors)}',flush=True)
manifest=[]
def copy(source,dest=None):
 p=SRC/source; target=dest or source
 assert not p.is_symlink() and p.is_file()
 write(target,'') if p.suffix not in ('.woff2',) else (DST/target).parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(p,DST/target)
 manifest.append({'source':source,'destination':target,'source_sha256':sha(p)})
for name in ['backend/__init__.py','backend/app/__init__.py','backend/app/agents/__init__.py','backend/app/services/__init__.py','backend/app/agents/content.py','backend/app/agents/revision.py','backend/app/workflow.py']:
 copy(name)
for name in ['providers','text_budget','visual_direction','artwork','background_check','assets','renderer','quality','data_lock','local_security']:
 copy(f'backend/app/services/{name}.py')
for name in ['__init__.py','themes.py','platforms.py','editorial-v1.css','spotlight-v1.css','bulletin-v1.css']:
 copy('backend/app/templates/'+name)
for name in ['contracts.py','models.py','config.py','database.py']:
 copy('backend/app/'+name)
copy('backend/alembic.ini'); copy('backend/migrations/env.py')
for name in ['inter-latin-600-normal.woff2']:
 copy('frontend/node_modules/@fontsource/inter/files/'+name,'assets/fonts/'+name)
copy('frontend/node_modules/@fontsource/inter/LICENSE','assets/fonts/LICENSE')
for name in ['01-machine-learning.json','02-generative-ai.json','03-cybersecurity.json','04-data-science.json','05-ai-trends.json','README.md']:
 copy('demo_reports/'+name,'tests/fixtures/reports/'+name)
for name in ['test_content','test_artwork','test_templates','test_platform_exports','test_distinct_creatives','test_natural_revision','test_provider_failures','test_text_reliability','test_visual_direction','test_poster_output_audit','test_hashtags']:
 copy('backend/tests/'+name+'.py')
# Extract reviewed shared definitions without altering their bodies.
def select_defs(source, names):
 text=(SRC/source).read_text(encoding='utf-8'); lines=text.splitlines(keepends=True); tree=ast.parse(text)
 out=[]
 for node in tree.body:
  if isinstance(node,(ast.Import,ast.ImportFrom)) or getattr(node,'name',None) in names:
   start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])-1
   out.append(''.join(lines[start:node.end_lineno]))
 return '\n\n'.join(out)+'\n'
write('backend/app/models.py',select_defs('backend/app/models.py',{'now_iso','Base','Campaign','ResearchRun','GenerationJob','Asset','ContentItem','ContentVersion'}))
p=DST/'backend/app/contracts.py'; text=p.read_text(); tree=ast.parse(text); lines=text.splitlines(keepends=True)
remove={'DashboardView','AgentSetting','HealthView','PermanentDeleteRequest','PermanentDeleteResult','CampaignView','CampaignPage'}
for n in reversed(tree.body):
 if getattr(n,'name',None) in remove: del lines[n.lineno-1:n.end_lineno]
p.write_text(''.join(lines),encoding='utf-8')
p=DST/'backend/app/config.py'; text=p.read_text(); tree=ast.parse(text); lines=text.splitlines(keepends=True)
for n in tree.body:
 if isinstance(n,ast.ClassDef) and n.name=='Settings':
  for field in reversed(n.body):
   if isinstance(field,ast.AnnAssign) and isinstance(field.target,ast.Name) and field.target.id.startswith(('research_','search_','meta_','cloudinary_')):
    del lines[field.lineno-1:field.end_lineno]
text=''.join(lines)
text=text.replace("return (path if path.is_absolute() else ROOT / path).resolve()", "resolved = (path if path.is_absolute() else ROOT / path).resolve()\n        if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():\n            raise ValueError('APP_DATA_DIR must be a subdirectory inside this standalone project.')\n        return resolved")
p.write_text(text,encoding='utf-8')
p=DST/'backend/app/services/renderer.py'; text=p.read_text().replace("ROOT / 'frontend/node_modules/@fontsource/inter/files/inter-latin-600-normal.woff2'","ROOT / 'assets/fonts/inter-latin-600-normal.woff2'").replace('Install frontend dependencies before rendering.','Restore assets/fonts/inter-latin-600-normal.woff2 before rendering.'); p.write_text(text,encoding='utf-8')
# Select content routes, excluding deletion/trash routes. Retain original code otherwise.
source='backend/app/content_api.py'; raw=(SRC/source).read_text(encoding='utf-8'); lines=raw.splitlines(keepends=True); tree=ast.parse(raw)
exclude={'delete_content','trash_content','restore_content','set_trash'}
for n in reversed(tree.body):
 if getattr(n,'name',None) in exclude:
  start=min([n.lineno]+[d.lineno for d in getattr(n,'decorator_list',[])])-1
  del lines[start:n.end_lineno]
text=''.join(lines).replace('PermanentDeleteRequest, PermanentDeleteResult, ','').replace('from .services.content_deletion import permanently_delete\n','')
text=text.replace("    from .approval_api import review\n    approval_status=review(db,item,version).approval_status","    approval_status='unapproved'")
text=text.replace("'approval_status':approval_status,","'approval_status':approval_status,'publishing_status':'not_published',")
text=text.replace("        from .approval_api import review\n        checked=review(db,item,version,request.app.state.workflow.assets)\n        if checked.blockers: raise HTTPException(409,'Cannot restore this version: '+' '.join(checked.blockers))", "        # Verify saved render integrity locally; no approval/publishing subsystem is included.\n        try:\n            for asset_id in saved.get('renders', []): request.app.state.workflow.assets.read(asset_id)\n        except (ProviderError, OSError):\n            raise HTTPException(409, 'A saved render is missing or failed its integrity check.') from None")
write(source,text); manifest.append({'source':source,'destination':source,'source_sha256':sha(SRC/source)})
# Isolated migration preserves reviewed current table definitions and version triggers.
write('backend/migrations/versions/0001_content_standalone.py', '''"""Initial standalone content schema; no research/publishing job tables."""
from alembic import op
from backend.app.models import Base
revision = 'content_0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("CREATE TRIGGER content_versions_no_update BEFORE UPDATE ON content_versions BEGIN SELECT RAISE(ABORT, 'Content versions are immutable'); END")
    op.execute("CREATE TRIGGER content_versions_no_delete BEFORE DELETE ON content_versions WHEN NOT EXISTS (SELECT 1 FROM content_items WHERE id=OLD.item_id AND trashed_at IS NOT NULL AND deleted_at IS NOT NULL) BEGIN SELECT RAISE(ABORT, 'Content versions are immutable'); END")

def downgrade():
    raise RuntimeError('Destructive downgrade is not supported; use a fresh standalone data directory.')
''')
write('EXTRACTION_MANIFEST.json',json.dumps(manifest,indent=2))
print(f'Copied {len(manifest)} allowlisted source files. No source writes.',flush=True)
