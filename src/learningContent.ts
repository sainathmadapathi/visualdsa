import type { Problem, Value } from './types';

// The hypotheses a learner can commit to. Must match TECHNIQUES in app.py (checked by tests).
export const techniques = ['Direct iteration / brute force', 'Hash map / set', 'Two pointers', 'Sliding window', 'Binary search', 'Running best / running total',
  'Linked-list pointer rewiring', 'Stack', 'Queue / deque', 'Breadth-first search', 'Depth-first search', 'Recursion / backtracking',
  'Heap / priority queue', 'Trie (prefix tree)', 'Dynamic programming', 'Bit manipulation'];

// Public teaching examples, independent of hidden evaluation cases.
export const contrastingExamples: Record<string, { args: Value[]; expected: Value; why: string }> = {
  'two-sum': { args: [[4, 4], 8], expected: [0, 1], why: 'Equal values can occupy different positions. Return the indices, not the values.' },
  'contains-duplicate': { args: [[6, 8, 10]], expected: false, why: 'Every value occurs once, so no duplicate exists.' },
  'pair-count': { args: [[4, 4, 4], 8], expected: 3, why: 'The distinct index pairs are (0,1), (0,2), and (1,2).' },
  'frequency-map': { args: [[8, 8, 3]], expected: { '8': 2, '3': 1 }, why: 'Each key is an input value; its associated value is the count.' },
  'unique-values': { args: [[5, 5, 5]], expected: [5], why: 'Only one distinct value exists. Output order is irrelevant.' },
  'intersection': { args: [[4, 6], [6, 6, 8]], expected: [6], why: '6 is shared by both arrays and appears once in the output.' },
  'first-unique': { args: ['aabbc'], expected: 4, why: 'c occurs once and occupies zero-based position 4.' },
  'valid-anagram': { args: ['aab', 'abb'], expected: false, why: 'The same distinct letters are insufficient: their counts differ.' },
  'palindrome': { args: ['Aa'], expected: false, why: 'Uppercase A and lowercase a differ. Comparisons are exact.' },
  'reverse-string': { args: ['ab c'], expected: 'c ba', why: 'Spaces are characters too and move with the reversal.' },
  'move-zeroes': { args: [[0, 8, 0, 4]], expected: [8, 4, 0, 0], why: '8 stays before 4. Modify the original list before returning it.' },
  'remove-duplicates': { args: [[2, 2, 2, 9]], expected: [2, 9], why: 'Each distinct value remains exactly once in sorted order.' },
  'sorted-squares': { args: [[-6, -2, 1]], expected: [1, 4, 36], why: 'Squaring changes relative order. The result must still be sorted.' },
  'merge-sorted': { args: [[2, 4], [2, 3]], expected: [2, 2, 3, 4], why: 'Both copies of 2 belong in the merged result.' },
  'two-sum-sorted': { args: [[1, 4, 7], 8], expected: [0, 2], why: '1 + 7 = 8. Return their zero-based positions.' },
  'binary-search': { args: [[2, 4, 8], 5], expected: -1, why: 'The target is absent, so there is no matching index.' },
  'search-insert': { args: [[2, 4, 8], 5], expected: 2, why: '5 belongs between 4 and 8, at position 2.' },
  'first-occurrence': { args: [[2, 4, 4, 8], 4], expected: 1, why: 'There are two matches; the first is at position 1.' },
  'last-occurrence': { args: [[2, 4, 4, 8], 4], expected: 2, why: 'There are two matches; the last is at position 2.' },
  'max-window-sum': { args: [[-6, -2, -4], 2], expected: -6, why: 'The valid sums are -8 and -6. A negative answer is still the maximum.' },
  'average-window': { args: [[4, 8, 2], 2], expected: 6, why: 'The averages are 6.0 and 5.0. Return the largest as a float.' },
  'longest-unique': { args: ['abba'], expected: 2, why: 'ab and ba are valid length-2 substrings. abb repeats b.' },
  'best-profit': { args: [[9, 6, 2]], expected: 0, why: 'Every later sale loses money. A profitable transaction is not required.' },
  'max-subarray': { args: [[-7, -2, -5]], expected: -2, why: 'For nonempty input choose a nonempty subarray; [-2] is best.' },
  'reverse-list': { args: [[4]], expected: [4], why: 'A single node is already reversed: its next pointer stays None.' },
  'merge-two-lists': { args: [[1, 1], [1]], expected: [1, 1, 1], why: 'Equal values all stay; every node appears once in the merged list.' },
  'valid-parentheses': { args: ['(]'], expected: false, why: 'Every bracket is closed, but by the wrong type.' },
  'daily-temperatures': { args: [[50, 50, 51]], expected: [2, 1, 0], why: 'An equal temperature is not warmer, so day 0 waits two days.' },
  'recent-calls': { args: [['RecentCounter', 'ping', 'ping'], [[], [1], [3002]]], expected: [null, 1, 1], why: 'At 3002 the window is [2, 3002], so the ping at 1 no longer counts.' },
  'window-max': { args: [[5, 4, 3], 2], expected: [5, 4], why: 'The 5 leaves after the first window, so 4 becomes the maximum.' },
  'kth-largest': { args: [[3, 3, 2], 2], expected: 3, why: 'Duplicates count: the two largest values are 3 and 3.' },
  'last-stone': { args: [[4, 4]], expected: 0, why: 'Equal stones destroy each other, leaving nothing.' },
  'subsets': { args: [[]], expected: [[]], why: 'Even an empty list has one subset: the empty subset.' },
  'permutations': { args: [[1]], expected: [[1]], why: 'One value has exactly one ordering.' },
  'max-depth': { args: [[]], expected: 0, why: 'An empty tree has no nodes, so its depth is 0.' },
  'level-order': { args: [[1, null, 2]], expected: [[1], [2]], why: 'A missing child is skipped; 2 still forms the second level.' },
  'implement-trie': { args: [['Trie', 'insert', 'search', 'startsWith'], [[], ['apple'], ['app'], ['app']]], expected: [null, null, false, true], why: 'app is a prefix of a stored word, but not a stored word itself.' },
  'prefix-counts': { args: [['hi', 'hi'], ['hi']], expected: [2], why: 'Each copy of a word counts separately.' },
  'count-components': { args: [[[], [], []]], expected: 3, why: 'With no edges, every node is a group of its own.' },
  'shortest-path': { args: [[[1], [0], []], 0, 2], expected: -1, why: 'Node 2 has no edges, so it cannot be reached.' },
  'count-islands': { args: [[[1, 0], [0, 1]]], expected: 2, why: 'Diagonal cells are not connected: these are two islands.' },
  'shortest-grid-path': { args: [[[0, 1], [1, 0]]], expected: -1, why: 'Diagonal moves are not allowed, so the corner cannot be reached.' },
  'climb-ways': { args: [0], expected: 1, why: 'Doing nothing is the one way to climb zero steps.' },
  'house-robber': { args: [[2, 1, 1, 2]], expected: 4, why: 'Take the first and last houses: skipping two in a row is allowed.' },
  'single-number': { args: [[0, 5, 5]], expected: 0, why: 'The single value can be 0; the answer is a value, not a position.' },
  'count-bits': { args: [0], expected: [0], why: 'The list includes 0 itself, which has no 1 bits.' },
};

// Input rules of the data-structure labs, as the server enforces them.
const structureRules: Record<string, string[]> = {
  'reverse-list': ['A linked list is written as its values from head to tail; [] is an empty list (head is None).'],
  'merge-two-lists': ['Both lists are sorted in nondecreasing order and written from head to tail.', 'Reuse the existing nodes: splice them, rather than building new ones.'],
  'valid-parentheses': ['The string contains only ( ) [ ] { }. An empty string is valid.'],
  'recent-calls': ['The first operation creates RecentCounter; each ping gets one time, and times strictly increase.', 'The window [t − 3000, t] includes both ends.'],
  'window-max': ['1 ≤ k ≤ array length. Windows are contiguous and move one position at a time.'],
  'kth-largest': ['1 ≤ k ≤ array length. Duplicates count separately.'],
  'last-stone': ['Stone weights are integers from 1 to 1,000.'],
  'subsets': ['At most 8 distinct values. Subsets may be returned in any order; each keeps the input order of its values.'],
  'permutations': ['At most 6 distinct values. Orderings may be returned in any order.'],
  'max-depth': ['A tree is written level by level with None for a missing child; [] is an empty tree.'],
  'level-order': ['A tree is written level by level with None for a missing child; [] is an empty tree.'],
  'implement-trie': ['The first operation creates Trie; every other operation gets one word of 1 to 20 lowercase letters.'],
  'prefix-counts': ['Words and queries are 1 to 20 lowercase letters; queries are not empty.'],
  'count-components': ['graph[i] lists the neighbours of node i (at most 30 nodes); every edge appears in both lists.'],
  'shortest-path': ['graph[i] lists the neighbours of node i (at most 30 nodes); every edge appears in both lists.', 'start and goal are node numbers.'],
  'count-islands': ['The grid is a non-empty rectangle of 0s and 1s, at most 12 × 12. Diagonal cells are not connected.'],
  'shortest-grid-path': ['The grid is a non-empty rectangle of 0s and 1s, at most 12 × 12. Moves go up, down, left or right.'],
  'climb-ways': ['0 ≤ n ≤ 40.'],
  'house-robber': ['Amounts are integers from 0 to 10,000.'],
  'single-number': ['Exactly one value appears once; every other value appears exactly twice.'],
  'count-bits': ['0 ≤ n ≤ 150.'],
};

export function constraintsFor(p: Problem): string[] {
  if (p.custom) return [p.decoder.returns, 'Your expected outputs are this lab’s answer key: it checks your code against them and cannot tell whether they are right.', 'Lab limits: at most 200 items per list and 200 characters per string.'];
  const rules = [p.decoder.returns, 'Lab limits: at most 200 items per array or 200 characters per string.', 'Numeric inputs are integers between −1,000,000 and 1,000,000; keep the example’s parameter types.'];
  if (['two-sum-sorted', 'binary-search', 'search-insert', 'first-occurrence', 'last-occurrence', 'sorted-squares', 'remove-duplicates', 'merge-sorted'].includes(p.id)) rules.unshift(p.id === 'merge-sorted' ? 'Both arrays must be sorted in nondecreasing order.' : 'The input array must be sorted in nondecreasing order.');
  if (['max-window-sum', 'average-window'].includes(p.id)) rules.unshift('1 ≤ k ≤ array length. Elements in a window are contiguous.');
  if (p.example.args.some(v => typeof v === 'string')) rules.unshift('Characters are compared exactly: case and spaces matter.');
  if (['two-sum', 'two-sum-sorted', 'pair-count'].includes(p.id)) rules.unshift('Use different positions. Equal values at different positions are allowed.');
  if (p.id === 'move-zeroes') rules.unshift('Modify the list in place and preserve the order of nonzero values.');
  if (structureRules[p.id]) rules.unshift(...structureRules[p.id]);
  return rules;
}
