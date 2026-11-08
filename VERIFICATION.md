# Extraction verification

Completed offline acceptance on 2026-11-08 in `C:\Users\HP\OneDrive\Desktop\Content Agent`.

## Result

The independent content-only project exists. It imports, initializes an isolated migrated database, accepts caller-supplied research contracts, runs the fixture-tested persistent content workflow and renders posters using local Chromium. Live text/artwork provider availability, quotas, model eligibility and credentials were deliberately not tested. This is verified offline functionality, not a claim of successful live generation.

Original source at `D:\Projects\AI_Social_Media` was never edited, imported, installed into, started, tested or migrated. No Git branch/commit/history changes were made. All extraction scripts, adaptations, dependencies, browser downloads, temporary files, test storage and reports were written inside the new folder.

## Commands actually executed in the copy

| Check | Actual result |
|---|---|
| Python AST parsing | 41 initial copied/adapted modules parsed; subsequent acceptance modules imported/collected through pytest. |
| Dedicated module imports | Standalone host, content/revision agents, workflow, artwork, renderer and quality imported successfully. |
| `python -m pip check` | No broken requirements found. |
| `tools/run_tests.ps1 -q --collect-only` | 120 tests collected successfully. |
| `tools/run_tests.ps1 -q --junitxml=verification/pytest-results.xml` | 120 tests; 0 failures; 0 errors; 0 skipped; 346.407 seconds. |
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

Reviewed HEAD and final HEAD both equal `7b220c9d6b3946ceee583e202cb49da3dd2085ea`. Reviewed and final Git status are clean. All 264 tracked-file SHA-256 hashes match the original reviewed baseline. A broader scan covered 22081 original regular files, including ignored configuration, runtime data, dependencies and Git files: no added, removed or changed paths, and no read errors.

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

`EXTRACTION_MANIFEST.json` records hashes for all 49 copied source/assets/fixture/test files: 40 unchanged and 9 adapted. Destination-only code and documentation are identified by the tree/README. Adaptation diffs are under `verification/adaptations/`.

## Recipient setup and remaining limitations

Use Python 3.12, create a fresh `.venv` when transferring, install `requirements.txt` and Chromium, and create a new `.env` from the blank `.env.example`. Supply your own eligible free-tier credentials and source-backed ResearchReport JSON. Read `README.md` for import, generation, progress, outputs and orchestration interfaces.

The local extraction is already installed for this Windows machine, but virtual environments and browser caches should not be transferred as portable installations. Exclude `.venv`, `.cache`, test-only generated `data/`, and any future `.env` from a handoff archive. An empty independent `data/app.sqlite3` was initialized by a separate normal-worker startup/shutdown smoke check; it contains no reports, generation jobs or content. The test suite uses its own isolated databases. See `verification/runtime-startup.json`. Quality/OCR checks still require human factual and visual review. The friend must implement exact-version human approval and publishing separately. Live provider checks remain manual and were intentionally outside this extraction.

## Exact copied-file inventory

| Original file | Independent destination | Treatment |
|---|---|---|
| `backend/__init__.py` | `backend/__init__.py` | Unchanged |
| `backend/app/__init__.py` | `backend/app/__init__.py` | Unchanged |
| `backend/app/agents/__init__.py` | `backend/app/agents/__init__.py` | Unchanged |
| `backend/app/services/__init__.py` | `backend/app/services/__init__.py` | Unchanged |
| `backend/app/agents/content.py` | `backend/app/agents/content.py` | Unchanged |
| `backend/app/agents/revision.py` | `backend/app/agents/revision.py` | Unchanged |
| `backend/app/workflow.py` | `backend/app/workflow.py` | Unchanged |
| `backend/app/services/providers.py` | `backend/app/services/providers.py` | Unchanged |
| `backend/app/services/text_budget.py` | `backend/app/services/text_budget.py` | Unchanged |
| `backend/app/services/visual_direction.py` | `backend/app/services/visual_direction.py` | Unchanged |
| `backend/app/services/artwork.py` | `backend/app/services/artwork.py` | Unchanged |
| `backend/app/services/background_check.py` | `backend/app/services/background_check.py` | Unchanged |
| `backend/app/services/assets.py` | `backend/app/services/assets.py` | Unchanged |
| `backend/app/services/renderer.py` | `backend/app/services/renderer.py` | Adapted; see recorded diff |
| `backend/app/services/quality.py` | `backend/app/services/quality.py` | Unchanged |
| `backend/app/services/data_lock.py` | `backend/app/services/data_lock.py` | Unchanged |
| `backend/app/services/local_security.py` | `backend/app/services/local_security.py` | Unchanged |
| `backend/app/templates/__init__.py` | `backend/app/templates/__init__.py` | Unchanged |
| `backend/app/templates/themes.py` | `backend/app/templates/themes.py` | Unchanged |
| `backend/app/templates/platforms.py` | `backend/app/templates/platforms.py` | Unchanged |
| `backend/app/templates/editorial-v1.css` | `backend/app/templates/editorial-v1.css` | Unchanged |
| `backend/app/templates/spotlight-v1.css` | `backend/app/templates/spotlight-v1.css` | Unchanged |
| `backend/app/templates/bulletin-v1.css` | `backend/app/templates/bulletin-v1.css` | Unchanged |
| `backend/app/contracts.py` | `backend/app/contracts.py` | Adapted; see recorded diff |
| `backend/app/models.py` | `backend/app/models.py` | Adapted; see recorded diff |
| `backend/app/config.py` | `backend/app/config.py` | Adapted; see recorded diff |
| `backend/app/database.py` | `backend/app/database.py` | Unchanged |
| `backend/alembic.ini` | `backend/alembic.ini` | Unchanged |
| `backend/migrations/env.py` | `backend/migrations/env.py` | Unchanged |
| `frontend/node_modules/@fontsource/inter/files/inter-latin-600-normal.woff2` | `assets/fonts/inter-latin-600-normal.woff2` | Unchanged |
| `frontend/node_modules/@fontsource/inter/LICENSE` | `assets/fonts/LICENSE` | Unchanged |
| `demo_reports/01-machine-learning.json` | `tests/fixtures/reports/01-machine-learning.json` | Unchanged |
| `demo_reports/02-generative-ai.json` | `tests/fixtures/reports/02-generative-ai.json` | Unchanged |
| `demo_reports/03-cybersecurity.json` | `tests/fixtures/reports/03-cybersecurity.json` | Unchanged |
| `demo_reports/04-data-science.json` | `tests/fixtures/reports/04-data-science.json` | Unchanged |
| `demo_reports/05-ai-trends.json` | `tests/fixtures/reports/05-ai-trends.json` | Unchanged |
| `demo_reports/README.md` | `tests/fixtures/reports/README.md` | Unchanged |
| `backend/tests/test_content.py` | `backend/tests/test_content.py` | Adapted; see recorded diff |
| `backend/tests/test_artwork.py` | `backend/tests/test_artwork.py` | Unchanged |
| `backend/tests/test_templates.py` | `backend/tests/test_templates.py` | Unchanged |
| `backend/tests/test_platform_exports.py` | `backend/tests/test_platform_exports.py` | Unchanged |
| `backend/tests/test_distinct_creatives.py` | `backend/tests/test_distinct_creatives.py` | Unchanged |
| `backend/tests/test_natural_revision.py` | `backend/tests/test_natural_revision.py` | Adapted; see recorded diff |
| `backend/tests/test_provider_failures.py` | `backend/tests/test_provider_failures.py` | Unchanged |
| `backend/tests/test_text_reliability.py` | `backend/tests/test_text_reliability.py` | Adapted; see recorded diff |
| `backend/tests/test_visual_direction.py` | `backend/tests/test_visual_direction.py` | Unchanged |
| `backend/tests/test_poster_output_audit.py` | `backend/tests/test_poster_output_audit.py` | Unchanged |
| `backend/tests/test_hashtags.py` | `backend/tests/test_hashtags.py` | Adapted; see recorded diff |
| `backend/app/content_api.py` | `backend/app/content_api.py` | Adapted; see recorded diff |

Final post-test confirmation: `verification/final-source-confirmation.json` rechecks HEAD, clean status and all 264 tracked hashes after the passing final test run. One-time extraction scripts/inputs are retained under `verification/extraction-tools/` as non-runtime audit records.
