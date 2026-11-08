from pathlib import Path
import shutil, json, hashlib, difflib
D=Path.cwd();S=Path(r'D:\Projects\AI_Social_Media')
shutil.copyfile(D/'verification/pytest-results.xml',D/'verification/pytest-initial-results.xml')
p=D/'backend/tests/test_text_reliability.py';t=p.read_text();start=t.index("        item=client.get('/api/v1/content').json()['items'][0]");end=t.index('\n\n\ndef test_correction_survives_capacity_wait',start);t=t[:start]+t[end:];p.write_text(t,encoding='utf-8')
# Keep provenance current for this destination-only test adaptation.
m=json.loads((D/'EXTRACTION_MANIFEST.json').read_text())
r=next(r for r in m if r['destination']=='backend/tests/test_text_reliability.py');r['destination_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();r['copied_unchanged']=False
r['adaptation_diff']='verification/adaptations/backend__tests__test_text_reliability.py.diff'
(D/r['adaptation_diff']).write_text(''.join(difflib.unified_diff((S/r['source']).read_text().splitlines(keepends=True),p.read_text().splitlines(keepends=True),fromfile='original/'+r['source'],tofile='standalone/'+r['destination'])),encoding='utf-8')
(D/'EXTRACTION_MANIFEST.json').write_text(json.dumps(m,indent=2))
p=D/'finish_extraction.py';t=p.read_text();t=t.replace('approval/purge assertions from the natural-revision test, and relocated','approval/purge assertions from the natural-revision test, deletion/purge assertions from the checkpoint/restart test, and relocated');t=t.replace('## What the tests cover','The first full run had 119 passed and one failure: an overlooked original deletion-only assertion called an intentionally excluded Trash endpoint after its content checkpoint/restart assertions had passed. That destination-only assertion block was removed as planned; no application logic changed. The complete final run above verifies the adapted suite. Raw initial results are retained in `verification/pytest-initial-results.xml`.\n\n## What the tests cover');p.write_text(t,encoding='utf-8')
print('Removed excluded deletion-only assertions and recorded the test adaptation.')
