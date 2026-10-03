export type Value = string | number | boolean | null | Value[] | { [key: string]: Value };
export interface Problem {
  id: string; number: number; title: string; category?: string; difficulty: string; params: string[];
  statement: string; decoder: { given: string; find: string; returns: string };
  example: { args: Value[]; expected: Value }; starter: string; discovery: (string | null)[]; hints: string[];
  recall: string[]; transfer: string | null; complexity: { time: string; space: string } | null;
  modification?: Modification;
  /** For a built-in lab the server sends only what the learner's own recorded work has opened: the topic after a
   * commitment; recall and the changed requirement once `unlocked` (a commitment or a passing run); reasoning
   * prompts 3–4 once revealed (null until then); hints up to the level asked for, out of `hintCount`. */
  hintCount?: number; recallCount?: number; unlocked?: boolean; hasModification?: boolean;
  /** A lab the learner defined for a row of their own sheet: their cases are its only answer key. */
  custom?: boolean; sheetId?: string; sheetName?: string; cases?: LabCase[]; order?: 'exact' | 'any'; returnsNote?: string;
  /** Which inputs are linked lists or trees, and the class a design problem builds (otherwise solve). */
  kinds?: Record<string, string>; entry?: string; methods?: Record<string, string[]>; sourceUrl?: string;
  /** How answers compare: the returned node's value, or printed lines without trailing spaces. */
  answer?: 'node-value' | 'lines' | null;
}
export interface LabCase { name: string; args: Value[]; expected: Value; explanation?: string }
/** One problem of a learner's sheet. `match` is a built-in lab (exact title/link match, close relative or
 * chosen by hand); `lab` is the learner's own lab for it. */
/** `url` is where the sheet lists the problem: its page on the sheet's own site when there is one (`source`).
 * `links` are the other links attached to it (LeetCode, GfG), used only when the problem can't be read on that site. */
export interface SheetRow { title: string; url: string; source?: string; links?: string[]; difficulty: string; topic: string; match: string | null; fit: 'same' | 'close' | 'manual' | null; lab: string | null }
/** A problem read from its page, exactly as stated there; `missing` marks an example whose output the page doesn't give as a value. */
/** One example as the page writes it, and whether it could become a case. */
export interface SourceExample { name: string; input: string; output: string; explanation: string; status: 'parsed' | 'partial' | 'unparsed' | 'duplicate'; issue: string | null; images?: number }
export interface FetchedProblem { title: string; statement: string; params: string[]; cases: { name: string; args: Value[]; expected: Value; missing: boolean; explanation?: string }[]; notes: string[]; source: string;
  description: string; sections: { heading: string; text: string }[]; constraints: string[]; examples: SourceExample[]; images: number; truncated: boolean; answer?: 'node-value' | 'lines' | null;
  kinds: Record<string, string>; entry: string; methods: Record<string, string[]> }
export interface Sheet { id: string; name: string; source: 'file' | 'link' | 'image' | 'paste'; origin: string; rows: SheetRow[]; created_at: string; updated_at: string }
export interface SheetDraft { id?: string; name: string; source: Sheet['source']; origin: string; rows: SheetRow[] }
/** A changed requirement: same inputs, a different output contract. Its solution and tests stay on the server. */
export interface Modification {
  id: string; title: string; statement: string; returns: string; question: string; hints: string[]; hintCount?: number;
  example: { args: Value[]; expected: Value };
}
export type Verdict = 'match' | 'alternative' | 'partial' | 'starting-point' | 'different';
export interface Commitment { technique: string; verdict: Verdict; operation: string; guided: boolean; reasons: string[]; transferFrom?: string | null }
export interface ApproachFeedback {
  verdict: Verdict; chosen: string; summary: string; gap: string; resolved: string[]; unresolved: string[];
  intended: { technique: string; operation: string; why: string };
  guided: boolean; reasons: string[]; first: boolean; firstCommitment: Commitment;
}
export interface Evidence {
  problem_id: string; kind: 'approach' | 'modified' | 'transferred'; created_at: string;
  detail: Partial<Commitment> & { requirement?: string; reasoning?: string; insight?: string; to?: string; toTitle?: string; prompted?: boolean };
}
/** A node of the learner's own structure, as recorded: its label, links (next, left, …) and children. */
export interface NodeRec { id: number; label: Value; cls: string; links: Record<string, number | null>; kids: [Value, number][]; attrs: Record<string, Value> }
export interface Structure {
  id: string; type: 'array' | 'string' | 'hashmap' | 'hashset' | 'matrix' | 'graph' | 'nodes'; values?: Value[];
  length?: number;
  entries?: { key: Value; value: Value }[]; highlights?: number[]; pointers?: Record<string, number>;
  /** How the program uses a sequence: as a stack, a queue, or a heap. */
  kind?: 'stack' | 'queue' | 'heap' | null;
  /** For a sequence of nodes: which recorded node each item is. */
  nodeRefs?: (number | null)[];
  /** A grid or table: its rows, shape, and the cell just read. */
  rows?: Value[][]; shape?: [number, number]; hot?: [number, number][];
  /** A graph: node labels and edges [from, to, weight]. */
  labels?: Value[]; edges?: [number, number, Value][]; directed?: boolean;
  /** Linked lists, trees and tries: the nodes, and which variable points at which node. */
  nodes?: NodeRec[]; refs?: Record<string, number | null>;
}
export interface TraceEvent {
  id: number; type: string; line: number; source: string; detail: string;
  meta: { expression?: string; left?: Value; right?: Value; result?: boolean | number; found?: boolean | null; value?: Value; structure?: string; key?: Value; targets?: string[]; index?: string; loop?: string;
    access?: FailedAccess; cycle?: Cycle; op?: string;
    call?: { id: number; fn: string; args: Record<string, Value>; depth: number }; ret?: { id: number; value: Value } };
  state: { structures: Structure[]; variables: { id: string; value: Value }[]; callstack: string[] };
  explanation: { what: string; why: string };
}
export interface Run {
  preview?: boolean;
  traceId?: string;
  truncated?: boolean;
  events: TraceEvent[]; result: Value; expected: Value; passed: boolean; error: { type: string; message: string; line: number | null } | null;
  tests: { name: string; args: Value[]; actual: Value; expected: Value; passed: boolean; error: { message: string } | null }[];
  counts: Record<string, number>; durationMs: number; stdout: string; attemptId: string;
  divergence: Divergence | null;
  /** The reference result for this exact input (live previews); never a test pass. */
  goal?: { expected: Value; matches: boolean } | null;
  /** How many times each line ran, from the line tracer. */
  lines?: Record<string, number>;
  /** Every case of the problem, each traced on the same code; `caseId` is this run's case. */
  cases?: CaseTrace[]; caseId?: string; input?: Value[];
}
/** One input of the case deck: the example, an authored edge case, or the learner's own input. */
export interface CaseTrace {
  id: string; name: string; custom: boolean; input: Value[];
  events: TraceEvent[]; result: Value; error: Run['error']; truncated?: boolean; lines?: Record<string, number>;
  goal?: Run['goal']; divergence: Divergence | null; counts: Record<string, number>; traceId: string; stdout?: string; durationMs?: number;
}
export interface FailedAccess { structure: string; key: Value; index: string; size: number; kind: 'dict' | 'sequence' }
export interface Cycle { line: number; first: number | null; repeat: number | null }
export interface WrongElement { position: number; value: Value; goal: Value; step: number; line: number; unchanged: boolean }
export interface Divergence {
  kind: string; message: string; step: number | null; line?: number | null;
  origin?: { step: number; line: number; name: string; unchanged: boolean } | null;
  access?: FailedAccess | null; cycle?: Cycle; elements?: { name: string; wrong: WrongElement[]; missing: number; ordered: boolean } | null;
}
export type Stage = 'Seen' | 'Understood' | 'Reproduced' | 'Explained' | 'Modified' | 'Independent' | 'Transferred';
export type Tab = 'understand' | 'discover' | 'code' | 'reflect';
