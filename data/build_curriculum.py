"""Authoring source for the initial 24 problem laboratories. No generated AI traces."""
import json
from pathlib import Path

problems = []


def add(id_, title, category, params, statement, given, find, returns, args, expected, cases, solution, brute, observations, hints, recall, transfer, time_, space_, level="Easy"):
    solution = 'def solve(' + params + '):\n' + '\n'.join('    ' + line for line in solution.strip().splitlines()) + '\n'
    brute = 'def solve(' + params + '):\n' + '\n'.join('    ' + line for line in brute.strip().splitlines()) + '\n'
    starter = f'def solve({params}):\n    # {find}\n    # {returns}\n    # Start with your simplest idea.\n    \n    pass\n'
    tests = [{"name": "Example", "args": args, "expected": expected}] + [{"name": name, "args": inputs, "expected": output} for name, inputs, output in cases]
    problems.append({"id": id_, "number": len(problems) + 1, "title": title, "category": category, "difficulty": level, "params": params.split(', '), "statement": statement, "decoder": {"given": given, "find": find, "returns": returns}, "example": {"args": args, "expected": expected}, "tests": tests, "starter": starter, "solution": solution, "brute": brute, "discovery": observations, "hints": hints, "recall": recall, "transfer": transfer, "complexity": {"time": time_, "space": space_}})


add('two-sum', 'Two Sum', 'Arrays', 'nums, target',
    'Find two different positions in an array whose values add up to the target. Return their zero-based indices, in either order. Return [] if no pair exists.',
    'A list of numbers and a target total.', 'Find two different elements that add up to the target.', 'Return their positions, not their values.',
    [[2, 7, 11, 15], 9], [0, 1], [('Repeated values', [[3, 3], 6], [0, 1]), ('No pair', [[1, 2, 4], 8], []), ('Negative values', [[-3, 4, 7], 1], [0, 1])],
    '''seen = {}
for i, x in enumerate(nums):
    need = target - x
    if need in seen:
        return [seen[need], i]
    seen[x] = i
return []''',
    '''for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        if nums[i] + nums[j] == target:
            return [i, j]
return []''',
    ['Start with every possible pair. How can you avoid using the same position twice?', 'The inner loop repeatedly searches for a partner. Up to n(n−1)/2 pairs are checked.', 'For a current value x, the only useful partner is target − x.', 'Remember earlier values and their positions. One lookup replaces a repeated search.'],
    ['The two numbers must occupy different positions. Values may repeat.', 'Fix one value. What other value would make the target?', 'For x = 2 and target = 9, the partner must be 7.', 'What would be worth remembering about earlier elements?', 'A dictionary can map each earlier value to its index.', 'Check for the partner before storing the current element, so you cannot reuse the same index.', 'For each i, x: calculate need, look up need, then store x → i.'],
    ['Why do we return indices instead of values?', 'Why must the lookup happen before the insert?', 'What does need represent?'], 'two-sum-sorted', 'O(n) expected', 'O(n)')

add('contains-duplicate', 'Contains Duplicate', 'Arrays', 'nums', 'Return True if any value appears at least twice; otherwise return False.', 'A list that may contain repeated values.', 'Find whether a value appears more than once.', 'Return a boolean, True or False.', [[1, 2, 3, 1]], True, [('All distinct', [[1, 2, 3]], False), ('Empty', [[]], False), ('Repeated zero', [[0, 0]], True)],
    '''seen = set()
for x in nums:
    if x in seen:
        return True
    seen.add(x)
return False''',
    '''for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        if nums[i] == nums[j]:
            return True
return False''', ['Compare every pair.', 'Many comparisons ask the same question: have I seen this value?', 'Remember the values, rather than repeatedly scanning.', 'A set stores membership without needing a position.'], ['What does a duplicate mean?', 'An earlier copy is enough to prove a duplicate.', 'Can you remember everything already processed?', 'Use a set to check membership.', 'Check x in seen before adding x.'], ['Why is adding before checking incorrect?', 'Do we need to remember indices?'], 'frequency-map', 'O(n) expected', 'O(n)')

add('pair-count', 'Count Matching Pairs', 'Hash maps', 'nums, target', 'Count all index pairs i < j whose values add up to target. Equal values at different positions count separately.', 'Numbers and a target.', 'Count matching pairs of different positions.', 'Return an integer count.', [[1, 1, 2, 2], 3], 4, [('Duplicates', [[3, 3, 3], 6], 3), ('No pair', [[2, 5], 9], 0), ('Empty', [[], 4], 0)],
    '''counts = {}
total = 0
for x in nums:
    total += counts.get(target - x, 0)
    counts[x] = counts.get(x, 0) + 1
return total''',
    '''total = 0
for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        if nums[i] + nums[j] == target:
            total += 1
return total''', ['Enumerate every distinct index pair.', 'The same needed partner is searched for repeatedly.', 'Existence alone is not enough: how many earlier partners exist?', 'Store frequencies and add the earlier partner count.'], ['Two 1s and two 2s make four pairs.', 'Fix the second position and count earlier partners.', 'What changed compared with Two Sum?', 'Store counts instead of a single index.', 'Add the frequency of target − x before incrementing the frequency of x.'], ['Why does a single saved index lose information?', 'Why count partners before saving the current value?'], 'two-sum', 'O(n) expected', 'O(n)', 'Medium')

add('frequency-map', 'Count Frequencies', 'Hash maps', 'nums', 'Return a dictionary mapping each number to how often it occurs.', 'A list of possibly repeated numbers.', 'Count the occurrences of each value.', 'Return a dictionary: value → count.', [[2, 7, 2, 4, 7, 2]], {'2': 3, '7': 2, '4': 1}, [('Empty', [[]], {}), ('One value', [[9]], {'9': 1}), ('Zeros', [[0, 0]], {'0': 2})],
    '''counts = {}
for x in nums:
    counts[x] = counts.get(x, 0) + 1
return counts''',
    '''counts = {}
for x in nums:
    counts[x] = nums.count(x)
return counts''', ['Count each value by scanning the list.', 'Repeated values cause repeated full scans.', 'An earlier count can be incremented.', 'One pass can update a dictionary.'], ['The dictionary key is the value, not its position.', 'What should the count be the first time you see a value?', 'Each new occurrence adds one.', 'get(x, 0) handles values not seen yet.'], ['Why do unseen values start at zero?', 'How much work does nums.count do?'], 'first-unique', 'O(n) expected', 'O(n)')

add('unique-values', 'Keep Unique Values', 'Hash maps', 'nums', 'Return every distinct value once. Output order does not matter.', 'Numbers that may repeat.', 'Keep only one copy of each distinct value.', 'Return a list with no repeats.', [[2, 2, 7, 4, 7]], [2, 7, 4], [('Empty', [[]], []), ('One repeated value', [[5, 5, 5]], [5])],
    '''seen = set()
result = []
for x in nums:
    if x not in seen:
        result.append(x)
        seen.add(x)
return result''',
    '''result = []
for x in nums:
    if x not in result:
        result.append(x)
return result''', ['Use an output list and search it before adding.', 'Searching an ever-growing list repeats work.', 'Only membership is needed.', 'A set lets us check previously added values.'], ['Output order is not constrained.', 'A repeated value must not be appended again.', 'A set is useful for membership tests.', 'Keep the set and output list in sync.'], ['Why is list membership more expensive as output grows?', 'What would change if output had to be sorted?'], 'intersection', 'O(n) expected', 'O(n)')

add('intersection', 'Array Intersection', 'Hash maps', 'nums, other', 'Return the distinct values present in both arrays. Order does not matter.', 'Two lists of numbers.', 'Find values that occur in both lists.', 'Return each common value once.', [[1, 2, 2, 4], [2, 2, 3]], [2], [('No overlap', [[1], [2]], []), ('Empty input', [[], [3]], []), ('Several shared', [[1, 2, 3], [3, 1]], [1, 3])],
    '''available = set(nums)
result = []
for x in other:
    if x in available:
        result.append(x)
        available.remove(x)
return result''',
    '''result = []
for x in nums:
    if x in other and x not in result:
        result.append(x)
return result''', ['Search the second array for each first-array value.', 'Repeated linear searches are the bottleneck.', 'Keep membership information about one input.', 'Remove matched entries to avoid repeated output.'], ['A common value must appear in both arrays.', 'A value should appear only once in the result.', 'Remember one array in a set.', 'Remove a value after adding it to output.'], ['Why remove a value after matching?', 'How would you preserve duplicate counts?'], 'pair-count', 'O(n + m) expected', 'O(n)')

add('first-unique', 'First Unique Character', 'Strings', 'text', 'Return the zero-based position of the first character occurring exactly once. Return -1 if none exists. Character matching is case sensitive.', 'A string of characters.', 'Find the first character with just one occurrence.', 'Return its index, or -1.', ['loveleetcode'], 2, [('None unique', ['aabb'], -1), ('Empty', [''], -1), ('First unique', ['abc'], 0)],
    '''counts = {}
for ch in text:
    counts[ch] = counts.get(ch, 0) + 1
for i, ch in enumerate(text):
    if counts[ch] == 1:
        return i
return -1''',
    '''for i, ch in enumerate(text):
    if text.count(ch) == 1:
        return i
return -1''', ['Count occurrences for each candidate.', 'Counting again for every position repeats scans.', 'A frequency table can be built once.', 'Scan positions in original order to find the first count of one.'], ['First refers to input order.', 'A unique character has a total count of one.', 'Count everything before deciding uniqueness.', 'Use a dictionary, then scan the original string again.'], ['Why is one early occurrence not enough to prove uniqueness?', 'Why not scan dictionary keys for the answer?'], 'valid-anagram', 'O(n) expected', 'O(n)')

add('valid-anagram', 'Valid Anagram', 'Strings', 'text, other', 'Return True when the two strings contain exactly the same characters with the same counts. Matching is case sensitive and spaces count.', 'Two strings.', 'Check whether the character counts match.', 'Return True or False.', ['anagram', 'nagaram'], True, [('Different counts', ['aab', 'abb'], False), ('Different lengths', ['ab', 'abc'], False), ('Both empty', ['', ''], True)],
    '''if len(text) != len(other):
    return False
counts = {}
for ch in text:
    counts[ch] = counts.get(ch, 0) + 1
for ch in other:
    if counts.get(ch, 0) == 0:
        return False
    counts[ch] -= 1
return True''',
    '''return sorted(text) == sorted(other)''', ['Sorting makes equal characters line up.', 'Sorting needs more than a single pass.', 'Only the count of each character matters.', 'Count one string, then consume counts using the other.'], ['Order may differ, but repetitions must match.', 'Unequal lengths can never be anagrams.', 'Remember counts from the first string.', 'Decrease each matching count; reject a missing character.'], ['Why are equal sets of characters insufficient?', 'What does a count of zero mean during the second pass?'], 'first-unique', 'O(n) expected', 'O(n)')

add('palindrome', 'Is It a Palindrome?', 'Two pointers', 'text', 'Return True if text reads the same forwards and backwards. Compare characters exactly, including spaces and case.', 'A string.', 'Compare characters from opposite ends.', 'Return True or False.', ['racecar'], True, [('Not symmetric', ['hello'], False), ('Empty', [''], True), ('Even length', ['abba'], True)],
    '''left = 0
right = len(text) - 1
while left < right:
    if text[left] != text[right]:
        return False
    left += 1
    right -= 1
return True''',
    '''return text == text[::-1]''', ['Build the reversed string and compare.', 'The reversed copy uses additional memory.', 'Opposite characters are all we need to compare.', 'Move two positions inward after each matching pair.'], ['Compare the first and last characters.', 'What should happen immediately when they differ?', 'Move both positions toward the center.', 'Stop when the positions meet or cross.'], ['Why do we only need to inspect half the string?', 'What happens for an empty string?'], 'reverse-string', 'O(n)', 'O(1)')

add('reverse-string', 'Reverse a String', 'Two pointers', 'text', 'Return a new string with characters in reverse order.', 'A string.', 'Put its last character first, and so on.', 'Return the reversed string.', ['hello'], 'olleh', [('Empty', [''], ''), ('Single character', ['x'], 'x'), ('Spaces', ['a b'], 'b a')],
    '''chars = list(text)
left = 0
right = len(chars) - 1
while left < right:
    chars[left], chars[right] = chars[right], chars[left]
    left += 1
    right -= 1
return "".join(chars)''',
    '''result = ""
for ch in text:
    result = ch + result
return result''', ['Prepending each character produces reversed order.', 'Repeated string copies grow with the partial output.', 'A mutable character list allows swaps.', 'Exchange opposite positions, then join once.'], ['Strings cannot be edited at an index.', 'Try turning text into a list of characters.', 'Swap the two end values.', 'Move toward the middle, then join the list.'], ['Why convert the string to a list?', 'What changes for a mutable array input?'], 'palindrome', 'O(n)', 'O(n)')

add('move-zeroes', 'Move Zeroes', 'Two pointers', 'nums', 'Return the array with all zeroes moved to the end, keeping nonzero numbers in their original order. Modify the list in place before returning it.', 'Numbers, including zeroes.', 'Move zeroes without reordering the other values.', 'Return the modified array.', [[0, 1, 0, 3, 12]], [1, 3, 12, 0, 0], [('All zeroes', [[0, 0]], [0, 0]), ('No zeroes', [[1, 2]], [1, 2]), ('Empty', [[]], [])],
    '''left = 0
for i in range(len(nums)):
    if nums[i] != 0:
        nums[left], nums[i] = nums[i], nums[left]
        left += 1
return nums''',
    '''result = []
for x in nums:
    if x != 0:
        result.append(x)
while len(result) < len(nums):
    result.append(0)
for i in range(len(nums)):
    nums[i] = result[i]
return nums''', ['Copy nonzero values, then fill the remaining positions.', 'An extra array is avoidable.', 'Remember the next position for a nonzero value.', 'Swap each nonzero value into that next position.'], ['Nonzero values must keep their order.', 'One index reads; another marks the next output position.', 'Only advance the output position for a nonzero value.', 'Swap the nonzero value into the output position.'], ['What does left mean at each iteration?', 'Why is nonzero order preserved?'], 'remove-duplicates', 'O(n)', 'O(1) extra')

add('remove-duplicates', 'Remove Sorted Duplicates', 'Two pointers', 'nums', 'Given sorted numbers, return a list containing each distinct value once, in sorted order.', 'A sorted array.', 'Keep just one copy of each value.', 'Return a list of the distinct numbers.', [[1, 1, 2, 2, 3]], [1, 2, 3], [('Empty', [[]], []), ('All same', [[2, 2, 2]], [2]), ('Distinct', [[1, 3, 5]], [1, 3, 5])],
    '''if len(nums) == 0:
    return []
left = 1
for i in range(1, len(nums)):
    if nums[i] != nums[left - 1]:
        nums[left] = nums[i]
        left += 1
return nums[:left]''',
    '''result = []
for x in nums:
    if x not in result:
        result.append(x)
return result''', ['Keep an output list and avoid repeats.', 'Membership searches are repeated.', 'Sorting puts duplicates next to one another.', 'Only compare with the most recent retained value.'], ['Duplicates are adjacent because input is sorted.', 'Compare with the last retained value.', 'A write index marks the end of the unique prefix.', 'Return just that prefix.'], ['What useful property does sorting provide?', 'Why should we return a slice, not the entire mutated list?'], 'unique-values', 'O(n)', 'O(n) returned slice')

add('sorted-squares', 'Squares in Sorted Order', 'Two pointers', 'nums', 'Given sorted integers, return their squares in nondecreasing order.', 'Sorted numbers that may be negative.', 'Square every value and keep the output sorted.', 'Return a sorted list of squares.', [[-4, -1, 0, 3, 10]], [0, 1, 9, 16, 100], [('All negative', [[-5, -3, -1]], [1, 9, 25]), ('Empty', [[]], []), ('Repeats', [[-2, 2]], [4, 4])],
    '''result = [0] * len(nums)
left = 0
right = len(nums) - 1
for i in range(len(nums) - 1, -1, -1):
    if abs(nums[left]) > abs(nums[right]):
        result[i] = nums[left] * nums[left]
        left += 1
    else:
        result[i] = nums[right] * nums[right]
        right -= 1
return result''',
    '''result = []
for x in nums:
    result.append(x * x)
return sorted(result)''', ['Square everything and sort the result.', 'Squaring loses the original order around zero.', 'The largest absolute value is at one of the two ends.', 'Fill output from largest to smallest using those ends.'], ['A negative number may have the largest square.', 'Where are the largest absolute values in a sorted list?', 'Compare both end values.', 'Write the larger square at the end of the result.'], ['Why does ordinary left-to-right squaring fail?', 'Why fill output from the right?'], 'merge-sorted', 'O(n)', 'O(n)')

add('merge-sorted', 'Merge Sorted Arrays', 'Two pointers', 'nums, other', 'Both arrays are sorted. Return one sorted array containing every value from both arrays, including duplicates.', 'Two sorted lists.', 'Combine them in sorted order.', 'Return a new sorted array.', [[1, 3, 5], [2, 4, 6]], [1, 2, 3, 4, 5, 6], [('Empty first', [[], [1, 2]], [1, 2]), ('Duplicates', [[1, 1], [1]], [1, 1, 1]), ('Both empty', [[], []], [])],
    '''i = 0
j = 0
result = []
while i < len(nums) and j < len(other):
    if nums[i] <= other[j]:
        result.append(nums[i])
        i += 1
    else:
        result.append(other[j])
        j += 1
return result + nums[i:] + other[j:]''',
    '''return sorted(nums + other)''', ['Combine and sort both lists.', 'Sorting repeats ordering work already done.', 'The next smallest value must be at an unconsumed front.', 'Compare both fronts, then append whichever is smaller.'], ['Both inputs are already ordered.', 'Keep one position for each list.', 'Move only the position you selected.', 'Append the leftovers when one list runs out.'], ['Why can we append the remaining suffix directly?', 'Why move only one pointer per comparison?'], 'sorted-squares', 'O(n + m)', 'O(n + m)')

add('two-sum-sorted', 'Two Sum, Sorted', 'Two pointers', 'nums, target', 'Given a sorted array, return two different zero-based indices whose values sum to target. Return [] if no pair exists.', 'Sorted numbers and a target.', 'Find a pair that adds up to the target.', 'Return zero-based positions.', [[2, 7, 11, 15], 18], [1, 2], [('Same values', [[3, 3], 6], [0, 1]), ('No pair', [[1, 2], 8], []), ('Negatives', [[-5, -1, 3, 8], 2], [1, 2])],
    '''left = 0
right = len(nums) - 1
while left < right:
    total = nums[left] + nums[right]
    if total == target:
        return [left, right]
    if total < target:
        left += 1
    else:
        right -= 1
return []''',
    '''for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        if nums[i] + nums[j] == target:
            return [i, j]
return []''', ['Every pair still works as a starting point.', 'But this time, the input has useful order.', 'Moving left inward increases the smaller value; moving right inward decreases the larger one.', 'Eliminate impossible partners one end at a time.'], ['What is different from the original Two Sum?', 'Start with opposite ends.', 'If the sum is too small, which value should increase?', 'Move left for a small sum, right for a large sum.', 'Keep left < right to avoid reusing a position.'], ['Why is this unsafe on unsorted data?', 'Which candidates does a pointer move eliminate?'], 'two-sum', 'O(n)', 'O(1)')

search_discovery = ['Start by checking each position.', 'Sorted input gives a stronger observation.', 'A middle comparison rules out half the remaining positions.', 'Maintain a valid search interval and shrink it on every step.']
search_hints = ['Input order matters.', 'Look at the middle of the remaining interval.', 'If the middle value is too small, everything to its left is also too small.', 'Update one boundary and always make progress.', 'Use mid = (left + right) // 2.']
add('binary-search', 'Find in a Sorted Array', 'Binary search', 'nums, target', 'Return an index containing target in a sorted array, or -1 if absent. Any matching index is valid.', 'A sorted list and a target.', 'Find the target value.', 'Return its index, or -1.', [[1, 3, 5, 7, 9, 11, 13], 9], 4, [('Absent', [[1, 3, 5], 4], -1), ('Empty', [[], 7], -1), ('At boundary', [[2, 4, 6], 2], 0)],
    '''left = 0
right = len(nums) - 1
while left <= right:
    mid = (left + right) // 2
    if nums[mid] == target:
        return mid
    if nums[mid] < target:
        left = mid + 1
    else:
        right = mid - 1
return -1''',
    '''for i, x in enumerate(nums):
    if x == target:
        return i
return -1''', search_discovery, search_hints, ['Why must the boundaries move past mid?', 'Why does left <= right include a one-element interval?'], 'first-occurrence', 'O(log n)', 'O(1)')

add('search-insert', 'Search Insert Position', 'Binary search', 'nums, target', 'Return the first position where target could be inserted while preserving sorted order. If target exists, return its first index.', 'A sorted array and a value.', 'Find the first value at least as large as target.', 'Return an insertion index from 0 to len(nums).', [[1, 3, 5, 6], 2], 1, [('After the end', [[1, 3], 8], 2), ('Empty', [[], 4], 0), ('Duplicates', [[1, 3, 3, 5], 3], 1)],
    '''left = 0
right = len(nums)
while left < right:
    mid = (left + right) // 2
    if nums[mid] < target:
        left = mid + 1
    else:
        right = mid
return left''',
    '''for i, x in enumerate(nums):
    if x >= target:
        return i
return len(nums)''', search_discovery, search_hints + ['An equal value may still have an earlier equal neighbor.'], ['Why can len(nums) be a valid answer?', 'Why keep mid when its value equals target?'], 'first-occurrence', 'O(log n)', 'O(1)')

for id_, title, first in [('first-occurrence', 'First Occurrence', True), ('last-occurrence', 'Last Occurrence', False)]:
    add(id_, title, 'Binary search', 'nums, target', f'Return the {"first" if first else "last"} index of target in a sorted array. Return -1 if absent.', 'Sorted numbers, possibly with duplicates.', f'Find the {"leftmost" if first else "rightmost"} target.', 'Return its index, or -1.', [[1, 2, 2, 2, 4], 2], 1 if first else 3, [('Absent', [[1, 3], 2], -1), ('Empty', [[], 1], -1), ('All equal', [[2, 2, 2], 2], 0 if first else 2)],
        '''left = 0
right = len(nums) - 1
answer = -1
while left <= right:
    mid = (left + right) // 2
    if nums[mid] == target:
        answer = mid
''' + ('        right = mid - 1\n' if first else '        left = mid + 1\n') + '''    elif nums[mid] < target:
        left = mid + 1
    else:
        right = mid - 1
return answer''',
        '''answer = -1
for i, x in enumerate(nums):
    if x == target:
''' + ('        return i\n' if first else '        answer = i\n') + 'return answer', search_discovery, search_hints + [f'After a match, save it and keep searching to the {"left" if first else "right"}.'], ['Why is the first match not necessarily the answer?', 'Why save a candidate before shrinking the interval?'], 'last-occurrence' if first else 'first-occurrence', 'O(log n)', 'O(1)')

window_discovery = ['Add each continuous group of k elements.', 'Neighboring groups share k − 1 elements.', 'Only one value leaves and one enters.', 'Maintain a running total by subtracting the outgoing value and adding the incoming value.']
window_hints = ['A group must be contiguous, not arbitrary positions.', 'Compare two neighboring groups.', 'Which values are shared?', 'Reuse the sum of the previous group.', 'Add nums[i] and remove nums[i − k].']
add('max-window-sum', 'Maximum Window Sum', 'Sliding window', 'nums, k', 'Return the largest sum of any contiguous group of exactly k elements. k must be between 1 and the array length.', 'An array and a fixed group size k.', 'Find the largest total for a continuous group of size k.', 'Return an integer sum.', [[2, 1, 5, 1, 3, 2], 3], 9, [('Negative values', [[-4, -2, -1], 2], -3), ('Whole array', [[2, 3], 2], 5), ('One item window', [[1, 7, 2], 1], 7)],
    '''total = sum(nums[:k])
best = total
for i in range(k, len(nums)):
    total += nums[i] - nums[i - k]
    best = max(best, total)
return best''',
    '''best = sum(nums[:k])
for i in range(len(nums) - k + 1):
    best = max(best, sum(nums[i:i + k]))
return best''', window_discovery, window_hints, ['Why does each update remove nums[i − k]?', 'Why not initialize best to zero?'], 'average-window', 'O(n)', 'O(k) initial slice')

add('average-window', 'Maximum Window Average', 'Sliding window', 'nums, k', 'Return the maximum average of exactly k contiguous values. Return a floating-point number.', 'Numbers and a window size.', 'Find the largest average over a fixed-size range.', 'Return a float.', [[1, 12, -5, -6, 50, 3], 4], 12.75, [('One window', [[2, 4], 2], 3.0), ('Negative', [[-3, -1], 1], -1.0), ('One value', [[8], 1], 8.0)],
    '''total = sum(nums[:k])
best = total
for i in range(k, len(nums)):
    total += nums[i] - nums[i - k]
    best = max(best, total)
return best / k''',
    '''best = sum(nums[:k]) / k
for i in range(len(nums) - k + 1):
    best = max(best, sum(nums[i:i + k]) / k)
return best''', window_discovery, window_hints + ['Every group has the same divisor k.'], ['Why can we maximize sum before dividing?', 'How would variable window sizes change the reasoning?'], 'max-window-sum', 'O(n)', 'O(k) initial slice')

add('longest-unique', 'Longest Unique Substring', 'Sliding window', 'text', 'Return the length of the longest contiguous substring without repeated characters. Characters are case sensitive.', 'A string with possible repetitions.', 'Find the longest continuous range with unique characters.', 'Return the range length.', ['abcabcbb'], 3, [('All same', ['bbbbb'], 1), ('Empty', [''], 0), ('Skipping a repeat', ['abba'], 2)],
    '''seen = {}
left = 0
best = 0
for right, ch in enumerate(text):
    if ch in seen and seen[ch] >= left:
        left = seen[ch] + 1
    seen[ch] = right
    best = max(best, right - left + 1)
return best''',
    '''best = 0
for i in range(len(text)):
    seen = set()
    for j in range(i, len(text)):
        if text[j] in seen:
            break
        seen.add(text[j])
        best = max(best, j - i + 1)
return best''', ['Try every starting point and grow a valid substring.', 'Overlapping ranges repeat membership checks.', 'A repeated character only invalidates the prefix through its earlier occurrence.', 'Remember last positions and move the left boundary past a repeat.'], ['Substring means a continuous range.', 'Extend the right boundary until a repeat appears.', 'Which prefix has to leave to remove the repeat?', 'Save the last index of each character.', 'Never move the left boundary backwards.'], ['Why check seen[ch] >= left?', 'Why is the range length right − left + 1?'], 'first-unique', 'O(n) expected', 'O(n)', 'Medium')

add('best-profit', 'Best Time to Buy & Sell', 'Arrays', 'nums', 'Given daily prices, return the largest profit from one buy followed by one later sell. Return 0 if no profit is possible.', 'Prices in chronological order.', 'Find the most profitable buy-before-sell pair.', 'Return a nonnegative profit.', [[7, 1, 5, 3, 6, 4]], 5, [('Falling prices', [[7, 6, 4]], 0), ('Empty', [[]], 0), ('Rising', [[1, 2, 4]], 3)],
    '''if len(nums) == 0:
    return 0
lowest = nums[0]
best = 0
for price in nums:
    best = max(best, price - lowest)
    lowest = min(lowest, price)
return best''',
    '''best = 0
for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        best = max(best, nums[j] - nums[i])
return best''', ['Try every buy date and each later sell date.', 'For each sale, only the cheapest earlier price matters.', 'Remember that running minimum.', 'Update best profit while scanning in chronological order.'], ['You cannot sell before buying.', 'For a fixed sell date, what is the best buy price?', 'Only earlier prices are valid.', 'Remember the minimum price seen so far.'], ['Why can we not just subtract global min from global max?', 'What does the running minimum represent?'], 'max-subarray', 'O(n)', 'O(1)')

add('max-subarray', 'Maximum Subarray', 'Arrays', 'nums', 'Return the largest sum of a nonempty contiguous subarray. For empty input, return 0.', 'Numbers, possibly negative.', 'Choose a nonempty contiguous range with the largest total.', 'Return an integer sum.', [[-2, 1, -3, 4, -1, 2, 1, -5, 4]], 6, [('All negative', [[-3, -1, -2]], -1), ('Single', [[5]], 5), ('Empty', [[]], 0)],
    '''if len(nums) == 0:
    return 0
current = nums[0]
best = current
for i in range(1, len(nums)):
    current = max(nums[i], current + nums[i])
    best = max(best, current)
return best''',
    '''if len(nums) == 0:
    return 0
best = nums[0]
for i in range(len(nums)):
    total = 0
    for j in range(i, len(nums)):
        total += nums[j]
        best = max(best, total)
return best''', ['Try all ranges, extending each starting point.', 'Can a negative running prefix help a future range?', 'For each position, either extend the previous best ending range or start fresh.', 'Keep the best ending sum and the best overall sum separately.'], ['A range must be contiguous.', 'A negative prefix reduces every continuation.', 'Compare starting here with extending the prior range.', 'current is the best sum ending here; best is the best seen anywhere.'], ['Why is initializing best to zero wrong for all-negative input?', 'How do current and best differ?'], 'max-window-sum', 'O(n)', 'O(1)', 'Medium')

if __name__ == '__main__':
    destination = Path(__file__).with_name('problems.json')
    destination.write_text(json.dumps(problems, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Authored {len(problems)} problem laboratories: {destination}')
