import type { Problem, Value } from './types';

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
};

export function constraintsFor(p: Problem): string[] {
  const rules = [p.decoder.returns, 'Lab limits: at most 200 items per array or 200 characters per string.', 'Numeric inputs are integers between −1,000,000 and 1,000,000; keep the example’s parameter types.'];
  if (['two-sum-sorted', 'binary-search', 'search-insert', 'first-occurrence', 'last-occurrence', 'sorted-squares', 'remove-duplicates', 'merge-sorted'].includes(p.id)) rules.unshift(p.id === 'merge-sorted' ? 'Both arrays must be sorted in nondecreasing order.' : 'The input array must be sorted in nondecreasing order.');
  if (['max-window-sum', 'average-window'].includes(p.id)) rules.unshift('1 ≤ k ≤ array length. Elements in a window are contiguous.');
  if (p.example.args.some(v => typeof v === 'string')) rules.unshift('Characters are compared exactly: case and spaces matter.');
  if (['two-sum', 'two-sum-sorted', 'pair-count'].includes(p.id)) rules.unshift('Use different positions. Equal values at different positions are allowed.');
  if (p.id === 'move-zeroes') rules.unshift('Modify the list in place and preserve the order of nonzero values.');
  return rules;
}
