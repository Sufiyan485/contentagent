from pathlib import Path
import json, hashlib, xml.etree.ElementTree as ET
D=Path(__file__).resolve().parent
S=Path(r'D:\Projects\AI_Social_Media')
def write(name,text):
 p=D/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=ET.parse(D/'verification/pytest-results.xml').getroot()
suite=root.find('testsuite') if root.tag=='testsuites' else root
stats={k:suite.attrib[k] for k in ['tests','errors','failures','skipped','time']}
assert stats['failures']=='0' and stats['errors']=='0',stats
integrity=json.loads((D/'verification/original-integrity-result.json').read_text())
assert integrity['initial_reviewed_head']==integrity['final_head']
assert integrity['final_status']==integrity['initial_reviewed_status']
assert not any(integrity[k] for k in ['tracked_mismatches','extended_added','extended_removed','extended_changed','read_errors'])
manifest=json.loads((D/'EXTRACTION_MANIFEST.json').read_text())
for row in manifest: assert row['destination_sha256']==sha(D/row['destination']),row['destination']
derived=[]
for name in ['0001_foundation.py','0002_content_workflow.py','0003_immutable_versions.py','0005_content_trash.py','0006_permanent_deletion.py']:
 source='backend/migrations/versions/'+name
 derived.append({'source':source,'source_sha256':sha(S/source),'derived_destination':'backend/migrations/versions/0001_content_standalone.py','purpose':'Frozen content schema/constraints/version triggers only; no research or publishing job schema copied.'})
write('verification/derived-migration-sources.json',json.dumps(derived,indent=2))
copy_table='\n'.join('| `'+r['source']+'` | `'+r['destination']+'` | '+('Unchanged' if r['copied_unchanged'] else 'Adapted; see recorded diff')+' |' for r in manifest)
text=f'''# Extraction verification

Completed offline acceptance on 2026-11-08 in `C:\\Users\\HP\\OneDrive\\Desktop\\Content Agent`.

## Result

The independent content-only project exists. It imports, initializes an isolated migrated database, accepts caller-supplied research contracts, runs the fixture-tested persistent content workflow and renders posters using local Chromium. Live text/artwork provider availability, quotas, model eligibility and credentials were deliberately not tested. This is verified offline functionality, not a claim of successful live generation.

Original source at `D:\\Projects\\AI_Social_Media` was never edited, imported, installed into, started, tested or migrated. No Git branch/commit/history changes were made. All extraction scripts, adaptations, dependencies, browser downloads, temporary files, test storage and reports were written inside the new folder.

## Commands actually executed in the copy

| Check | Actual result |
|---|---|
| Python AST parsing | 41 initial copied/adapted modules parsed; subsequent acceptance modules imported/collected through pytest. |
| Dedicated module imports | Standalone host, content/revision agents, workflow, artwork, renderer and quality imported successfully. |
| `python -m pip check` | No broken requirements found. |
| `tools/run_tests.ps1 -q --collect-only` | 120 tests collected successfully. |
| `tools/run_tests.ps1 -q --junitxml=verification/pytest-results.xml` | {stats['tests']} tests; {stats['failures']} failures; {stats['errors']} errors; {stats['skipped']} skipped; {stats['time']} seconds. |
| Core provenance hashes | Content/revision agents, workflow, provider/artwork/storage/quality services remain byte-for-byte unchanged. Renderer diff changes only the bundled font path/setup message. |
| Secret-pattern and runtime-path scan | No findings; no original `.env` or `.git` copied; no original absolute runtime path in application modules. This is a heuristic scan plus reviewed allowlist, not a universal secret-detection guarantee. |
| Visual review | Inspected `data/verification/long-copy/instagram-bulletin-v1.png` and `data/verification/platforms/linkedin-editorial-v1.png`; text was readable with no visible clipping. |

Dependencies were installed in the new `.venv`; Chromium/FFmpeg and pip/temp caches live under its `.cache`. Software packages/browser binaries were downloaded, but no live generation, research, publishing, account, paid-service or purchase requests were made. The source environment was not reused. Direct package pins came from the reviewed source requirements; compatible transitive versions were independently resolved and then fully pinned. Some transitive versions differ from the main application's lock; the accepted standalone environment is recorded in `requirements-verified.txt`.

The first full run had 119 passed and one failure: an overlooked original deletion-only assertion called an intentionally excluded Trash endpoint after its content checkpoint/restart assertions had passed. That destination-only assertion block was removed as planned; no application logic changed. The complete final run above verifies the adapted suite. Raw initial results are retained in `verification/pytest-initial-results.xml`.

## What the tests cover

- Original content prompt/schema checks, claim IDs, hashtag rules, caption warnings, concept/slide limits and bounded correction behavior.
- Groq/provider throttling, scheduled retries and checkpoint preservation using fixture responses; missing credentials fail explicitly with no fixture fallback.
- Artwork prompt construction, configurable exclusions, bounded OCR rejection/retry, synthetic mocked Pollinations responses, local OCR rejection of lettering and acceptance of a blank image. No image-model API was contacted.
- Actual local gradient artwork and Chromium renders across three templates, three platform sizes and three themes; overflow rejection, header visibility/pixel stability and exact preview/export pixels.
- Shared and distinct-platform creative paths; exact background asset reuse within every carousel, per-platform retry preservation, manual/natural revisions and unchanged artwork after text edits.
- Isolated schema, immutable content versions, progress/retry history, optional caller-supplied campaign context, report import validation/conflict handling and no normal demo seeding.
- Retrieval after a fresh application instance and after a separately launched Python process, version restoration, interrupted-worker recovery and exact-version edit conflicts.
- Environment secret masking, in-project storage only, outside-path and junction-escape rejection, and absence of other agents' tables/workers/endpoints.

LLM responses and research were explicitly synthetic fixtures. Pollinations requests were mocked. Local OCR, Chromium, SQLite, gradients and persistence were real. The test bootstrap alone ingests the five labeled demo reports; the normal application rejects demo imports. Source report `origin=live` used by boundary tests is explicitly labeled synthetic and does not imply live research was performed.

## Source preservation evidence

Reviewed HEAD and final HEAD both equal `{integrity['final_head']}`. Reviewed and final Git status are clean. All {integrity['reviewed_tracked_count']} tracked-file SHA-256 hashes match the original reviewed baseline. A broader scan covered {integrity['extended_baseline_count']} original regular files, including ignored configuration, runtime data, dependencies and Git files: no added, removed or changed paths, and no read errors.

Machine-readable evidence is in `verification/original-integrity-result.json`, with baselines beside it. The broad baseline was captured before copying; the reviewed tracked baseline was captured during the initial inspection. Both scans read file bytes without importing source code or opening the original SQLite through a database connection.

Limitations: scans are sequential rather than atomic snapshots, cover file contents rather than every filesystem metadata attribute, and do not follow directory symlinks/junctions or file symlinks. No external process was stopped or locked. These checks establish no observed changes within their recorded scope; they cannot guarantee that an independently running program will never change the source later.

## Adaptations and exclusions

- New minimal content-only FastAPI startup; content worker only, localhost port 8001, independent settings and paths.
- Shared settings/models/contracts narrowed to required content/report/context types. Report snapshots and optional campaign rows are integration data, not copied agents.
- Content API route bodies retained, with deletion/trash endpoints and approval subsystem dependencies removed. Outputs are always unapproved/not published. Version restoration keeps source digest/background checks and locally checks render integrity without importing approval execution.
- Font moved into `assets/fonts` with the original license; no frontend dependencies copied.
- Frozen content-only initial Alembic migration derived from the reviewed migrations. `verification/derived-migration-sources.json` records the source hashes.
- Test bootstrap replaced by explicit standalone fixtures. Removed only original trash/restore assertions from `test_content.py`, approval/purge assertions from the natural-revision test, deletion/purge assertions from the checkpoint/restart test, and relocated the hashtag report fixture path. Other relevant content assertions remain.
- No Research/Coordinator/Publishing agent, social/OAuth/Cloudinary settings or clients, production database/content, original credentials, React UI, original environment or Git history was copied. No UI redesign was performed.

`EXTRACTION_MANIFEST.json` records hashes for all {len(manifest)} copied source/assets/fixture/test files: {sum(r['copied_unchanged'] for r in manifest)} unchanged and {sum(not r['copied_unchanged'] for r in manifest)} adapted. Destination-only code and documentation are identified by the tree/README. Adaptation diffs are under `verification/adaptations/`.

## Recipient setup and remaining limitations

Use Python 3.12, create a fresh `.venv` when transferring, install `requirements.txt` and Chromium, and create a new `.env` from the blank `.env.example`. Supply your own eligible free-tier credentials and source-backed ResearchReport JSON. Read `README.md` for import, generation, progress, outputs and orchestration interfaces.

The local extraction is already installed for this Windows machine, but virtual environments and browser caches should not be transferred as portable installations. Exclude `.venv`, `.cache`, test-only generated `data/`, and any future `.env` from a handoff archive. An empty independent `data/app.sqlite3` was initialized by a separate normal-worker startup/shutdown smoke check; it contains no reports, generation jobs or content. The test suite uses its own isolated databases. See `verification/runtime-startup.json`. Quality/OCR checks still require human factual and visual review. The friend must implement exact-version human approval and publishing separately. Live provider checks remain manual and were intentionally outside this extraction.

## Exact copied-file inventory

| Original file | Independent destination | Treatment |
|---|---|---|
{copy_table}
'''
write('VERIFICATION.md',text)
write('HANDOFF.txt','Start with README.md. Offline acceptance: '+stats['tests']+' tests passed. See VERIFICATION.md for evidence and limitations. No credentials are included.\n')
plan=D/'EXTRACTION_PLAN.md';old=plan.read_text();plan.write_text('> Approved by the user for execution on 2026-11-08. This is the preserved review-stage plan; see VERIFICATION.md for completed results.\n\n'+old,encoding='utf-8')
print('Wrote final verification and handoff reports; all acceptance gates passed.')
