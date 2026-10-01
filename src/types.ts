export type Value = string | number | boolean | null | Value[] | { [key: string]: Value };
export interface Problem {
  id: string; number: number; title: string; category: string; difficulty: string; params: string[];
  statement: string; decoder: { given: string; find: string; returns: string };
  example: { args: Value[]; expected: Value }; starter: string; discovery: string[]; hints: string[];
  recall: string[]; transfer: string; complexity: { time: string; space: string };
}
export interface Structure {
  id: string; type: 'array' | 'string' | 'hashmap' | 'hashset'; values?: Value[];
  length?: number;
  entries?: { key: Value; value: Value }[]; highlights?: number[]; pointers?: Record<string, number>;
}
export interface TraceEvent {
  id: number; type: string; line: number; source: string; detail: string;
  meta: { expression?: string; left?: Value; right?: Value; result?: boolean; found?: boolean; value?: Value; structure?: string; key?: Value };
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
  divergence: { kind: string; message: string; step: number } | null;
}
export type Stage = 'Seen' | 'Understood' | 'Reproduced' | 'Explained' | 'Modified' | 'Independent' | 'Transferred';
export type Tab = 'understand' | 'discover' | 'code' | 'reflect';
