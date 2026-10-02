# Visual DSA

A working local learning laboratory: understand a problem, discover an approach, write Python, inspect **your actual execution**, and transfer the reasoning to a related problem.

The homepage (`/`) explains the platform: every topic the laboratory draws in motion (17 cards, from arrays and hash maps
to linked lists, trees, graphs, DP tables and bits, listed in `src/topics.ts`), what Visual DSA is, its four modes and what the lab shows.
Choosing a topic opens the library on it: its built-in labs, any labs you built for it from your own sheets, and the sheets that
have its problems, each opening filtered to just that topic (rows are matched by their sheet topic, else their title). It contains no editor. The editor, live execution,
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

- 46 authored labs in 17 topics. 24 cover arrays, strings, hash maps/sets, two pointers, fixed and variable windows, and binary search. The other 22 cover the data structures, two each, written in `data/structures_curriculum.py`:
  - **Linked lists:** reverse, merge two sorted lists.
  - **Stacks:** valid parentheses, daily temperatures.
  - **Queues:** recent calls (a design class), sliding-window maximum.
  - **Heaps:** kth largest, last stone weight.
  - **Recursion:** subsets, permutations.
  - **Trees:** maximum depth, level order.
  - **Tries:** implement a trie (a design class), prefix counts.
  - **Graphs:** connected groups, fewest steps.
  - **Grids:** islands, shortest grid path.
  - **Dynamic programming:** climbing stairs, house robber.
  - **Bits:** single number, counting bits.

  Each has the same parts as the first 24: decoder, cases, a reference and a simple solution, discovery, hints, recall, an approach to commit to, and a changed requirement.
  - **Inputs:** linked lists and trees are written as judges write them and reach the code as nodes (`kinds`). Design problems build their class and call each operation (`entry`).
  - **Input rules:** every lab's inputs are checked on the server (`INPUT_RULES` in `app.py`).
  - **Techniques:** there are 16 to commit to, adding pointer rewiring, stack, queue/deque, BFS, DFS, recursion/backtracking, heap, trie, DP and bit manipulation.
  - **Sheet matching:** imported sheets match their rows to these labs, for example 37 rows of Striver's A2Z sheet.
- Problem decoders, examples, progressive hints, a four-step discovery path, technique-selection questions, written recall, and linked variations.
- Monaco Python editor, input editing, save/bookmark actions, and separate read-only simple/optimized reference approaches. Revealing an approach preserves the learner's draft.
- Real Python AST instrumentation in a separate process, immutable visual snapshots, SVG array/string/index and dictionary/set views, and GSAP transitions.
- Source-linked operations, comparisons and branch results, loops, reads/writes, dictionary operations, function frames, returns, and runtime errors.
- Play/pause, forward/backward, replay, scrub, speed selection, and an expandable event timeline.
- Example and edge-case checks, incorrect-result visualization, attempt-aware hints, a theoretical complexity experiment, and actual operation counts.
- SQLite code, bookmarks, attempts, trace history, learning evidence, and hint/reveal history. Passing evidence is required for execution-based stages. Lower stages cannot overwrite higher stages.
- Optional Firebase Google sign-in, identity verification, and draft/preference/progress-summary synchronization.
- Optional LLM explanations built from a **server-stored execution event**. Without credentials, a deterministic Trace guide explains the same event.
- **Your own sheet** (`/sheets`): import a problem list from a file, a link or a photo; matched rows open built-in labs, and the rest become labs the learner defines from the problem's examples (see below).

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

`app.py` intentionally contains the worker, instrumentation, state conversion, explanation adapter, SQLite, and Flask routes in separated sections. `data/build_curriculum.py` is the curriculum's authoring source, with the data-structure labs in `data/structures_curriculum.py`; running `python data/build_curriculum.py` regenerates `data/problems.json`. React UI components, typed API, Zustand store, and optional Firebase adapter live in `src`.

The next slices are stronger trace-aware diagnostic classification, validated reasoning assessments, independent transfer evidence, and specialized node/tree/graph/DP renderers. Their future scope is not represented as completed functionality. “Explained” currently records written self-review, rather than asserting that an AI has established mastery. A single trace's event count is not a proof of asymptotic complexity.

## Context-aware tutoring

The existing Flask `/api/chat` and `/api/explain` endpoints share server-side tutoring context: active stage, problem contract, current input and draft, recent conversation, notebook notes, persisted hint/progress levels, and selected/previous/next recorded events. Client-supplied event/state claims are ignored. Chat history is scoped to the current problem in the UI; hints survive a new chat through SQLite support records.

Live previews return an opaque `traceId`. The Flask process retains a bounded owner-scoped cache (up to 32 traces, approximately 16 MB serialized, 10-minute expiry) so the Guide can explain actual preview events without creating attempts or awarding mastery. The newest single trace is retained even if it exceeds that byte target. An expired trace or restarted server requires a new preview. Full attempts continue using existing SQLite execution sessions.

Observed execution explanations are deterministic, including concrete state differences, runtime failures and provable output-contract violations. A final mismatch is never presented as proof of the first faulty intermediate step. Optional AI coaches non-execution questions; it does not generate trace state or overwrite recorded observations. Without model credentials, stage-aware authored tutoring and progressive hints remain available.

Discover includes saved reasoning at each step, deliberately revealed prompts, and a candidate/read-count exercise with overlap feedback. These are clearly labeled teaching illustrations, separate from actual-code visualization. Reflect adds assumptions, decision justifications and counterexample prompts alongside the existing transfer plan.

## The learning loop: commit, debug, adapt, transfer

**Discover keeps the technique hidden until the learner commits.** The library lists problems without their technique unless the learner has committed an approach or chose a topic filter. Discover asks for the operation that must become fast, a technique hypothesis, a rationale and a plan. `/api/approach` then reveals the authored approach and compares the two: match, valid alternative, partial, correct starting point, or a different approach, with the specific reasoning gap. Checkpoints are lexical, so feedback reports what is *visible in the learner's notes*, never a judgment of understanding. The first commitment is kept as evidence. It is recorded as *guided* when the learner opened the problem from its topic, used hints or the guide, revealed a reference, or revealed reasoning prompts that point toward the approach. The approach specs live in `data/build_curriculum.py` and never reach the client before commitment.

**Failed tests close the debugging loop.** Failing tests open automatically, and each offers **Trace this input**, which runs the learner's current code on that exact input through `/api/execute`. One divergence finder serves the test runner and the guide. It reports a runtime error, a provable contract violation (including output-type mismatches), or the return step where a wrong value first becomes observable. It also reports which step last changed the returned variable. That is provenance, not blame: a mismatch is never presented as the first faulty step.

**Modify is a changed requirement, not a badge.** Each lab has an authored modification with the same inputs and a different output contract, its own reference and tests (for example, Two Sum → count every pair). The learner first writes what changes in their reasoning, then adapts their own solution in the same workbench. The original solution fails every modification on at least one test (`tests/test_learning_loop.py` proves it). *Modified* requires a passing attempt on the changed requirement, the learner's reasoning, and no revealed reference.

**Transfer is earned on the related problem.** *Transferred* is never requested directly. It is recorded on problem P when the learner had solved P before committing on its related problem Q, that first commitment was unaided and matched Q's approach, and Q then passes without a revealed reference.

Evidence of each kind lives in the SQLite `learning_evidence` table alongside the existing stage ladder, so a learner who reached *Independent* still has their modification and transfer recorded. A lower stage never overwrites a higher stage's evidence. Firestore synchronization still covers drafts, bookmarks and stages only.

**Preparing for cold practice.** Topic entry is remembered per problem, commitments record guided versus unaided context, and library labels are earned. A future cold mode can filter on this evidence without new tables.


## The visual stage

Code & Visualize animates the learner's own recorded run, inspired by classic algorithm animations. `src/visualModel.ts` makes every visual decision from the trace and nothing else, and `tests/visual_model.cjs` covers it.

- **Sequences** are lanes of cells. Pointer arrows glide between cells. A pointer is a variable the code actually used inside that list's brackets, or a classic name such as `left` that was never used as an index. Two paired pointers (`left`/`right`, `lo`/`hi`) shade the range between them. A two-element exchange is drawn as a swap: one value rises over the row and the other dips under it. Writes pop, with the old value floating away. Reads glow, and the reads that fed a comparison are ringed.
- **Dictionaries and sets** animate inserts, changed values, removals and lookups. A lookup shows a probe that reports found or not here.
- **Goal for this input.** Live previews also run the reference on the current input. The goal bar shows that result and, once the program returns, whether the learner's result matches it. It never runs tests, records attempts or awards progress.
- **Going in the wrong direction** is shown only where the trace proves it:
  - An out-of-range read becomes a ghost cell beyond the list. A missing key becomes a ghost row.
  - A `while` loop whose complete local state repeats (values and object sharing) is reported as a **proven infinite loop** at the repeat. Its two identical steps are linked. States holding iterators are never compared, because their position is hidden.
  - A wrong returned list is traced element by element to the write that put each wrong value into the final answer. It is marked on the execution ribbon as provenance, not as the cause.
  - "Nothing returned yet" is shown gently while a function is still being written.
- **Live coding.** A fresh preview opens on the line under the cursor. The line lens reports what that line did across the run (for example, `need = 7 → need = 2`), or that it never ran; per-line counts come from the line tracer. While you type, the last runnable trace is dimmed. An incomplete edit reports its line.
- **Motion** follows the system's reduced-motion setting until the learner changes the Motion switch, in the workbench or the top bar. The choice is stored on the device and applied as `html[data-motion]`.

### Every case, every update

Each problem has 5–6 authored cases: the example plus edge cases such as empty input, repeats, negatives and zero, boundaries, "no answer" and exact characters. Each live update, and each **Run all tests**, traces the learner's code on every case, plus their own input from Edit input. The worker runs all cases in a single process with a fresh namespace and its own time budget per case, so a live update still takes about 0.1 s and one runaway case cannot stop the others.

The visual pane's **case deck** shows a live ✓ / ✗ / ⚠ verdict for every case and a running "4/6 on target" count. Choosing a case animates that case's own trace from the start, and the choice is kept while the learner keeps typing. Each case carries a question that makes it worth thinking about. **Play every case** tours them back to back.

An explicit run still records its attempt and progress from the main input only. The authored cases appear as its tests, and both authored solutions are checked against every case.

## Your own sheet

`/sheets` lets a learner practice the problem list they already follow. A sheet can come from:

- **A file:** Excel (`.xlsx`, every tab is read and the tab name becomes the topic, and hyperlinked titles keep their links), CSV/TSV (including `=HYPERLINK(...)` cells), a text or Markdown list or table, or JSON.
- **A link:** a Google Sheet shared as "Anyone with the link" (read via its CSV export), a CSV/JSON/text file, a web page with a table or list of problem links, or a sheet site that embeds its list as page data (Next.js page data, server-component payloads, JSON script tags; schema-indexed row tables are expanded). Striver's A2Z sheet on takeuforward.org imports as 448 problems with its steps and sub-topics as topics; lessons and contests are skipped. The local Flask server fetches the link once. It refuses private and local addresses (including after redirects), responses over 3 MB, and slow hosts. A single problem link becomes a one-problem sheet titled as its page titles it (`Kadane's Algorithm`). A LeetCode link, or a page that can't be read, is named from its link instead (`leetcode.com/problems/two-sum/` → "Two Sum") and is never fetched.
- **A photo or screenshot:** text recognition (tesseract.js) runs in the browser, so the image is never uploaded. The first use downloads the recognition engine from a CDN. Serial numbers, status columns and the header row are dropped, and a title above the table becomes the sheet's name.
- **Pasted text:** a range copied straight from Excel or Google Sheets, or a plain list.

**The sheet's own site comes first.** A problem's link is its page on the site the sheet came from; for Striver's sheet that is takeuforward.org (`/practice/dsa/<slug>`, the route the site's own scripts build), and relative links on any sheet page resolve to that site. Links the sheet attaches to a problem (LeetCode, GeeksforGeeks) are kept as secondary "also" links and still match built-in labs. The sheet view says which site it tracks and links back to the original sheet, and practice links back to the problem there. Nothing is saved until the learner reviews every row: they can edit titles, untick rows, and choose which lab each row opens. Rows match a built-in lab only by exact normalised title or link slug. A **close** match (e.g. LeetCode's in-place or 1-indexed variant) is labelled, and its practice page says the contract differs.

For a row with no built-in lab, the learner **builds the lab**. They paste the problem's own examples ("Input: nums = [2,7], target = 9 / Output: [0,1]") or write the statement, the `solve` parameters, and cases with expected outputs. The builder suggests edge cases to add (empty input, one element, duplicates…); the learner writes their values. Their expected outputs are the lab's only answer key, and the lab says so: it has no reference solution, hints or authored approach, and nothing is invented. When the row has a readable page, the builder **reads the problem automatically** as it opens. It reads the problem on the sheet's own site first. Only if the problem can't be read there does it try the attached links in order, and it says which one it used. Sources are the problem's own page on the sheet's site (takeUforward rows keep it as `source`, so link-less rows like "Pattern 1" gain a link) or a non-LeetCode link such as a GeeksforGeeks problem. It fills in the title, the statement with its sections and constraints, the parameters and one case per example (see **Reading a problem page** below). A **Read this link** field reads the problem from any other page instead. One page is fetched per request and never in bulk, and the site's robots.txt is respected. LeetCode is not fetched, because it builds its pages in the browser. Everything else works on it: live tracing of every case in the case deck, the goal bar ("your case expects 6"), divergence, Run all tests, attempts and progress stages, Discover as an ungraded plan, Reflect and recall, and the guide. An input outside the learner's cases shows what the code does, never a verdict. Labs are scoped to their owner, and "Next in your sheet" continues down the list.

### Reading a problem page

The page is the authority. Extraction is deterministic (no model reads the page), and everything the page doesn't say is left for the learner rather than filled in.

- **What is read.** Reading starts at the page's main heading (a "Description" or "Problem Statement" heading continues it). It reads the description, keeping code blocks with their indentation, and labelled sections under their own headings: input/output format, notes, your task, expected complexity, follow-up, parameters, returns, edge cases. It also reads constraints, superscripts and subscripts (`10^5`, `arr_i`) and each example. Every example keeps its own input, output and explanation, as written, and the page's explanation travels with the case into practice ("From the problem's page: …").
- **What is left out.** Navigation, footers and asides; quizzes ("Now your turn", "Still unsure…"); hints, editorials, approaches, solutions and code; comments, tags and tables of contents; and a judge's sign-in or "submit your code" panel. The lab notes how many lines were left out. Section words (Code, Approach…) end the problem only as headings, so "Implementation must run in O(n)." stays in the statement.
- **Formats.** It reads HTML pages and problems a page keeps in its page data (GeeksforGeeks). It also reads Markdown READMEs, skipping front matter and link-only lines and keeping their inline HTML. Judges' notations are read as written, including:
  - `arr[] = {1, 2}`, `head -> 1 -> 2` and `Result:` used as the output label;
  - design operations written as calls: `[MedianFinder(), addNum(1), findMedian()]`;
  - in a tree's level order, a missing node written as `N`, which is read as `null`, and the example says so.

  Constraints that GeeksforGeeks draws from data are written out bound by bound (`1 ≤ arr.size() ≤ 10^5`), with a note saying where they came from.
- **Judges' notations for outputs and inputs.** A lab opens with the cases the page gives values for:
  - **Output values:** an output named after what is returned (`head = [1, 2]`) is that value. Numbers separated by spaces (`4 7`) are read as a list, as judges print one, and a lone number among them becomes a list of one. A bare word (`Yes`) is text, and values named after every input (`a = 10, b = 5`) are a list in that order.
  - **Output labels:** `Output = …` and `Output(value at returned node): …` are read. The latter compares the value of the node your function returns.
  - **Patterns:** a pattern the statement draws in text ("for N = 5 … like below") becomes a case of printed lines, compared without trailing spaces.
  - **Cycles:** `pos` next to a linked list builds the cycle and isn't passed to your function, as judges describe a loop.
  - **Inputs:** an unnamed input after a named one, a missing comma between inputs, and an unquoted text input are read.
  - **Notes:** each reading is said in the notes. Examples whose output can't be read stay listed, but don't become blank cases.
  - **Coverage:** on Striver's A2Z sheet, 442 of 448 problems open with every case filled (37 of them as built-in labs). The other 6 can't be filled faithfully: their inputs are images or unexplained codes, an example leaves out its input, the output is a check rather than a value, any valid order is accepted, or the input needs shared nodes.
- **What is never guessed.** An output shown as an image, a printed pattern, standard-input samples, and an input with a typo on the page (`[1, 4, null, 4 2]`) are kept word for word. Each gets a reason ("output needs you", "not read: enter by hand"), and the lab won't save until the learner writes the value. Duplicate examples are skipped and said. Images and statements cut at 12,000 characters are noted.
- **When nothing can be read.** A page built in the browser or with no problem on it fails with a message naming the site, and the fields stay as they were. The builder's "From the page" panel shows each example exactly as read and whether it became a case.

### Errors are always JSON

Every `/api/` response is JSON, including failures: `{"ok": false, "error": "<message for the learner>", "details": "<optional>"}` with an HTTP status. Bad input is 400, and routes that don't exist are 404. Oversized requests are 413, and unexpected crashes are 500 (logged on the server). The Vite dev proxy answers `502 {"ok": false, "error": "The learning API is not running…"}` when Flask isn't running, instead of an empty 500. `src/api.ts` reads every response as text before parsing it, so an empty or non-JSON body becomes a clear message, never "Unexpected end of JSON input".

Sheets live in SQLite (`sheets`, `custom_labs`). Removing a sheet removes its labs; attempts and progress remain as history. `sheets.py` holds the readers, matching and lab validation. `tests/test_sheets.py` covers them and the API, and `tests/test_extraction.py` covers faithful reading and the JSON contract.

## Every data structure in a sheet

The runner accepts ordinary interview-style Python, and the visual stage draws each data structure from the recorded run:

- **Programs:** functions, nested helpers and recursion; classes, including the learner's own `ListNode`/`TreeNode`/`TrieNode` and design classes; lambdas, keyword arguments, defaults and type hints (which are stripped); and `@cache`/`@lru_cache`. Imports are allowed from `collections`, `heapq`, `math`, `bisect`, `functools`, `itertools`, `typing`, `string` and `sys` (`setrecursionlimit` only). `ListNode`, `TreeNode` and `Node` are provided. A runtime guard allows any attribute on the learner's own objects but only safe methods on built-in values. Dunder attributes, `format`, frame and generator internals, file and network access, and `exec`/`eval` stay closed.
- **Inputs and outputs:** a lab marks each parameter as a value, a linked list, a doubly linked list, a binary tree (level order with `null`) or a list of linked lists. The sheet importer guesses this from arrows (`head -> 1 -> 2`), parameter names and the statement. The program receives real nodes, and a returned head or root is compared as judges write it: a list of values, with a tree in level order. Design problems (`["MinStack", "push", …]` with their arguments) build the class and call each operation in order.
- **What is recorded:** the node graph reachable from every active call, with which variable points at which node. Also recorded: grids and DP tables with the cell just read; graphs from adjacency lists, adjacency matrices and edge lists; how each list is used (stack, queue or heap); each call's arguments and return value; and every bit operation. A `while` loop over linked nodes that comes back to exactly the same state is proven infinite.
- **What is drawn** (`src/structureModel.ts` for layout, `src/components/StructureViews.tsx` for the views):
  - Linked lists sit in rows by chain: next arrows, back-arcs and prev arcs, `None` ends, and pointer badges such as `prev`, `curr` and `slow`. Re-linked edges redraw.
  - Binary trees are laid out by in-order position and depth. Tries and n-ary trees are centred over their children, with letter edges.
  - Grids show row and column pointers, with visited and queued cells and a heat tint for DP tables.
  - Graphs use a stable force layout coloured by the program's own `visited`, `dist` and `color` arrays and its queue or stack. The current node and the neighbour being tried are marked on the live edge.
  - Stacks are upright, queues run front to back, and heaps appear both as an array and as a tree.
  - Recursion shows as a call tree with return values and the running path; for a design problem it becomes an operation log.
  - Bit operations are shown bit by bit.

  - They are drawn in the homepage posters' language (`src/poster.css`): flat ink tiles with cream mono values, the ember next-pointer cell, pointer pills on a stem that glide from node to node, links and root-to-node paths that flow while they matter, a turning halo on the tree node the code holds, a ripple on the current graph node, plates in an open container, a conveyor tube for queues, and grids coloured by meaning (land, water, marked cells) or, for tables of numbers, in cream by size.

  Everything moves through transforms and path transitions, so the Motion switch stops it.

Live previews of these labs measured 110–250 ms from the last keystroke to the updated visual. `tests/test_structures.py` and `tests/structure_model.cjs` cover the engine and the layouts.
