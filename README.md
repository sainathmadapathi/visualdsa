# Visual DSA

A working local learning laboratory: understand a problem, discover an approach, write Python, inspect **your actual execution**, and transfer the reasoning to a related problem.

The homepage (`/`) is a discovery landing page. The editor, live execution,
learning stages, and playback live at `/practice?problem=two-sum`. Choose a
problem from the library, enter the laboratory, or follow a guide recommendation.
Browser back/forward and direct practice links are supported; drafts are preserved.

Each learning stage has its own workspace:
- **Understand:** input/output contracts, two explorable examples, prediction and reveal, and constraints.
- **Discover:** brute force through optimization, technique selection, reasoning notes, and a saved pseudocode notebook.
- **Code & Visualize:** Monaco and actual execution playback appear only here, with the saved approach available alongside the experiment.
- **Reflect & Transfer:** execution evidence, correctness and complexity reflection, written recall, and an adaptation plan carried into a related problem's separate code draft.

Stage changes preserve code and notes, pause playback, and cancel pending live previews outside the coding stage. Learning notes stay on this device.

## Run locally

From the project directory:

```powershell
npm install
python -m pip install -r requirements.txt
```

Start the API in one terminal:

```powershell
python app.py
```

Start the frontend in another:

```powershell
npm run dev
```

Open **http://127.0.0.1:5173**. No credentials are needed for local learning. Vite proxies `/api` to Flask on port 5000. `npm run build` creates `dist`; Flask also serves that built application at **http://127.0.0.1:5000**.

For one unified server, run `npm run build`, then `python app.py`, and open
**http://127.0.0.1:5000**. Rebuild after frontend edits and restart after Python edits.

## What is implemented

- 24 authored labs across arrays, strings, hash maps/sets, two pointers, fixed and variable windows, and binary search.
- Problem decoders, examples, progressive hints, a four-step discovery path, technique-selection questions, written recall, and linked variations.
- Monaco Python editor, input editing, save/bookmark actions, and separate read-only simple/optimized reference approaches. Revealing an approach preserves the learner's draft.
- Real Python AST instrumentation in a separate process, immutable visual snapshots, SVG array/string/index and dictionary/set views, and GSAP transitions.
- Source-linked operations, comparisons and branch results, loops, reads/writes, dictionary operations, function frames, returns, and runtime errors.
- Play/pause, forward/backward, replay, scrub, speed selection, and an expandable event timeline.
- Example and edge-case checks, incorrect-result visualization, attempt-aware hints, a theoretical complexity experiment, and actual operation counts.
- SQLite code, bookmarks, attempts, trace history, learning evidence, and hint/reveal history. Passing evidence is required for execution-based stages. Lower stages cannot overwrite higher stages.
- Optional Firebase Google sign-in, identity verification, and draft/preference/progress-summary synchronization.
- Optional LLM explanations built from a **server-stored execution event**. Without credentials, a deterministic Trace guide explains the same event.

## The first experiment

1. Open **Two Sum** and read the input/goal/output decoder.
2. Use **Discover** to reason about a simple pair search.
3. Write a `solve(nums, target)` function in Monaco. Ctrl+Enter runs it.
4. Pause and click **Timeline**. Select a condition or write; the source line and the matching visual snapshot update together.
5. Try `return [0, 0]`. The returned value stays `[0, 0]`; feedback explains why reusing a position violates the problem. Request a hint to see feedback about that actual attempt.
6. Explore the simple or optimized reference if needed, then return to **My draft**.
7. Explain the approach and try **Two Sum, Sorted**. The decoder updates its example and the related input property changes.

Playback inspects a completed trace, rather than rerunning the program at each step. Editing code marks the previous trace as stale. Editing input clears that trace. Reference executions never count as independent learner executions.

## Execution design

```text
learner source → validated AST → instrumented expressions/statements
             → dedicated Python worker → ordered events + frozen Visual State Model
             → SVG structures + source highlight + what/why explanation
```

Expression instrumentation evaluates operands once. Assignment events are captured **after** the write. CPython line tracing enforces execution budgets; it is not incorrectly treated as the state after a line, because [line events precede execution](https://docs.python.org/3/library/sys.html#sys.settrace).

The intermediate event/state contract is typed in `src/types.ts`. The renderer consumes this contract, not arbitrary Python locals or AI-generated animation instructions. Deterministic test validators accept alternate valid index pairs and order-independent set results where appropriate. A result mismatch does **not** pretend to locate a first logical divergence: it links to the actual result state and asks the learner to inspect their steps.

### Supported learning subset

Use plain functions including a function named `solve` with the displayed parameters. Lists, tuples, strings, dictionaries, sets, loops, comprehensions, recursion, conditions, arithmetic, and selected standard built-ins/methods are supported. No imports, classes, annotations, decorators, generators, async, underscore names, arbitrary attributes, indirect function calls, keyword call arguments, files, or network APIs. The UI's help dialog lists the scope.

Limits: 12,000 source characters, 200 input elements/characters, 1,200 recorded events, 15,000 traced ticks, a three-second internal budget, an eight-second parent timeout, bounded output and snapshot depth, and guarded large allocations. Worker memory is limited to 192 MiB; CPU to four seconds. Windows uses a Job Object with one active process and kill-on-close; Unix uses `resource` limits. Two simultaneous API executions are allowed.

**Local execution is a restricted development runner, not a complete OS security boundary.** The server binds to loopback. Public mode refuses local execution and requires the Docker runner and configured authentication.

### Container runner for public deployment

The worker image is provided, but Docker must be running before building or testing it:

```powershell
docker build -f Dockerfile.worker -t visual-dsa-worker .
$env:EXECUTION_MODE = "docker"
$env:APP_ENV = "production"
```

Each execution gets a fresh non-root container with a read-only filesystem, no network, no capabilities, `no-new-privileges`, 192 MiB memory, 0.5 CPU, and 16 PIDs. The parent cleans up containers after success or timeout. Use a production WSGI server behind HTTPS, configure Firebase Admin, and add perimeter request/rate limits before public exposure. Docker execution has not been verified on this host because its daemon is not running.

## Firebase (optional)

Copy `.env.example` to `.env`; populate the four `VITE_FIREBASE_*` settings. Enable Google in Firebase Authentication and authorize your local/deployment domain. Restart Vite after changing the file.

Install `requirements.txt`, then set server configuration before starting Flask:

```powershell
$env:FIREBASE_PROJECT_ID = "your-project-id"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\outside-the-repository\service-account.json"
python app.py
```

Deploy `firestore.rules` to your project. The frontend signs in with Google and sends Firebase ID tokens; the backend [verifies them using Firebase Admin](https://firebase.google.com/docs/auth/admin/verify-id-tokens). Credentials stay out of the browser and repository.

**Authority:** SQLite owns execution truth, test outcomes, hint/reveal history, attempts, and verified progress evidence. Firebase Authentication owns identity. Firestore stores small cross-device learning summaries, drafts, and bookmarks under `learners/{uid}/learning/{problemId}`; raw traces never go there. SQLite saves succeed even when optional cloud sync fails. Browser drafts are a convenience fallback, not execution evidence. Authentication/cloud behavior requires your project credentials and has not been verified against a live project.

## AI teaching layer (optional)

**Studio guide** is available on the landing and practice pages. `/api/chat`
retrieves relevant curriculum passages, topic explanations, examples, complexity
notes, and platform help using BM25-style lexical ranking, aliases, limited typo
matching, and recent-question context for follow-ups. This is a lightweight lexical
RAG pipeline, not an embedding model or a trained model. Retrieved passages are
visible in chat, with validated buttons into the relevant practice lesson.

When the existing `LLM_API_KEY` is configured, the model receives the retrieved
passages and recent conversation to compose contextual guidance. In practice,
the learner can include or exclude their draft, input and selected recorded step.
Execution evidence is loaded from the authenticated user's server-owned attempt;
client-supplied trace claims are ignored and stale code is identified. Hidden tests
and reference solution code are excluded from retrieval. Tutoring records assistance
without awarding mastery. Chat messages stay in page memory and are cleared by
New chat or a reload; the server does not persist the conversation.

Without credentials, **Knowledge mode** returns the relevant authored passage or
recorded-event explanation and clearly labels the limitation. It does not diagnose
arbitrary code or pretend to be a generative AI. Provider failures also fall back to
this mode. The provider integration is covered by mocked tests; a live model still
requires your server-side credentials. API keys must never use a `VITE_` prefix.

Set an OpenAI-compatible chat-completions endpoint on the backend:

```powershell
$env:LLM_API_KEY = "your-key"
$env:LLM_MODEL = "gpt-4.1-mini"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
python app.py
```

The selected problem, source, selected recorded event, previous event, result, and error are supplied as context. Credentials are server-only. AI failure falls back to the deterministic Trace guide. AI prose is advisory: it cannot change events, visual states, outputs, or tests. Live AI responses have not been verified without a key.

## Validate

Live preview is enabled by default. After an 850 ms typing pause, `/api/preview`
executes the current input in the same bounded worker and plays its recorded trace.
Editing stays enabled, requests are serialized, and stale results are discarded.
Incomplete source appears as quiet feedback beside the canvas. The Live switch
pauses automatic execution; **Run all tests** performs explicit validation.
Previews do not run the test suite, persist attempts, call AI, or award mastery.
Laboratory motion respects the system's reduced-motion preference. The topic
gallery uses continuous 3D motion, with automatic cycling and cursor parallax.

```powershell
npm run build
node --test tests/live_preview.cjs
python -m unittest discover -s tests -v
```

Tests check both authored algorithms against every curriculum test case, actual dictionary transitions, snapshot isolation, incorrect code preservation, swapping, single expression evaluation, runtime errors, execution/allocation limits, forbidden code, the subprocess boundary, API checks, persistence, and assistance-aware progress.

The browser was checked with real Monaco input for reference execution and an incorrect learner return, source-linked timeline selection, playback, and attempt-aware hints. The interface includes responsive navigation, keyboard shortcuts, labeled controls, native dialog focus trapping, and reduced-motion support.

## Files and expansion

`app.py` intentionally contains the worker, instrumentation, state conversion, explanation adapter, SQLite, and Flask routes in separated sections. `data/build_curriculum.py` is the curriculum's authoring source; running it regenerates `data/problems.json`. React UI components, typed API, Zustand store, and optional Firebase adapter live in `src`.

The next slices are stronger trace-aware diagnostic classification, validated reasoning assessments, independent transfer evidence, and specialized node/tree/graph/DP renderers. Their future scope is not represented as completed functionality. “Explained” currently records written self-review, rather than asserting that an AI has established mastery. A single trace's event count is not a proof of asymptotic complexity.

## Context-aware tutoring

The existing Flask `/api/chat` and `/api/explain` endpoints share server-side tutoring context: active stage, problem contract, current input and draft, recent conversation, notebook notes, persisted hint/progress levels, and selected/previous/next recorded events. Client-supplied event/state claims are ignored. Chat history is scoped to the current problem in the UI; hints survive a new chat through SQLite support records.

Live previews return an opaque `traceId`. The Flask process retains a bounded owner-scoped cache (up to 32 traces, approximately 16 MB serialized, 10-minute expiry) so the Guide can explain actual preview events without creating attempts or awarding mastery. The newest single trace is retained even if it exceeds that byte target. An expired trace or restarted server requires a new preview. Full attempts continue using existing SQLite execution sessions.

Observed execution explanations are deterministic, including concrete state differences, runtime failures and provable output-contract violations. A final mismatch is never presented as proof of the first faulty intermediate step. Optional AI coaches non-execution questions; it does not generate trace state or overwrite recorded observations. Without model credentials, stage-aware authored tutoring and progressive hints remain available.

Discover includes saved reasoning at each step, deliberately revealed prompts, and a candidate/read-count exercise with overlap feedback. These are clearly labeled teaching illustrations, separate from actual-code visualization. Reflect adds assumptions, decision justifications and counterexample prompts alongside the existing transfer plan.
