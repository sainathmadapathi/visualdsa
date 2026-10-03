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

# ----------------------------------------------------------------------------
# More edge cases. Each one asks a different question of the learner's code; every case is
# traced and animated live beside the editor (tests check both authored approaches pass).
# ----------------------------------------------------------------------------
EDGE_CASES = {
    'two-sum': [('Pair at the ends', [[1, 5, 9, 4], 5], [0, 3]), ('Target zero', [[-3, 7, 3], 0], [0, 2])],
    'contains-duplicate': [('Repeat at the far end', [[4, 1, 2, 4]], True), ('Negative repeat', [[-1, 2, -1]], True)],
    'pair-count': [('All one value', [[2, 2, 2, 2], 4], 6), ('Negatives and zero', [[-1, 1, 0, 0], 0], 2)],
    'frequency-map': [('Negatives', [[-1, -1, 2]], {'-1': 2, '2': 1}), ('All distinct', [[3, 1, 2]], {'3': 1, '1': 1, '2': 1})],
    'unique-values': [('Already unique', [[3, 1, 2]], [3, 1, 2]), ('Negatives and zero', [[0, -1, 0, -1]], [0, -1])],
    'intersection': [('One side repeats', [[5, 5, 5], [5]], [5]), ('Negatives', [[-2, 0, 3], [3, -2]], [3, -2])],
    'first-unique': [('Unique at the end', ['aabbc'], 4), ('Case matters', ['aA'], 0)],
    'valid-anagram': [('Case matters', ['Ab', 'ab'], False), ('Spaces count', ['a b', 'ba '], True)],
    'palindrome': [('Single character', ['x'], True), ('Case matters', ['Aa'], False)],
    'reverse-string': [('Palindrome input', ['abba'], 'abba'), ('Two characters', ['ab'], 'ba')],
    'move-zeroes': [('Zero at the end', [[1, 0]], [1, 0]), ('Zeroes first', [[0, 0, 0, 7]], [7, 0, 0, 0])],
    'remove-duplicates': [('Single value', [[4]], [4]), ('Negatives', [[-3, -3, -1, 0, 0]], [-3, -1, 0])],
    'sorted-squares': [('Zero in the middle', [[-2, 0, 2]], [0, 4, 4]), ('All positive', [[1, 2, 3]], [1, 4, 9])],
    'merge-sorted': [('One side longer', [[1], [2, 3, 4]], [1, 2, 3, 4]), ('Negatives', [[-5, 0], [-2]], [-5, -2, 0])],
    'two-sum-sorted': [('Pair at the ends', [[1, 3, 4, 6], 7], [0, 3]), ('Two elements', [[2, 5], 7], [0, 1])],
    'binary-search': [('Last element', [[1, 3, 5], 5], 2), ('Single element', [[4], 4], 0)],
    'search-insert': [('Before the start', [[3, 5], 1], 0), ('Single element', [[4], 5], 1)],
    'first-occurrence': [('Target at the end', [[1, 2, 3, 3], 3], 2), ('Single element', [[4], 4], 0)],
    'last-occurrence': [('Target at the start', [[1, 1, 2, 3], 1], 1), ('Single element', [[4], 4], 0)],
    'max-window-sum': [('Best window at the end', [[1, 1, 5, 6], 2], 11), ('All zeroes', [[0, 0, 0], 2], 0)],
    'average-window': [('Best at the start', [[9, 8, 1, 1], 2], 8.5), ('All equal', [[3, 3, 3], 2], 3.0)],
    'longest-unique': [('All different', ['abcd'], 4), ('Space counts', ['a a'], 2)],
    'best-profit': [('Single day', [[5]], 0), ('Dip, then peak', [[3, 8, 1, 9]], 8)],
    'max-subarray': [('All positive', [[1, 2, 3]], 6), ('Mixed signs', [[-1, 3, -2, 4]], 5)],
}
for p in problems:
    p['tests'] += [{'name': name, 'args': args, 'expected': expected} for name, args, expected in EDGE_CASES[p['id']]]

# ----------------------------------------------------------------------------
# Approach discovery. Server-only: revealed after the learner commits a hypothesis.
# `operation` is the work that must become fast; checkpoints are ideas a complete
# plan usually states. Detection is lexical, so feedback says "visible in your notes".
# ----------------------------------------------------------------------------
HASH, POINTERS, WINDOW, SEARCH, RUNNING, BRUTE = 'Hash map / set', 'Two pointers', 'Sliding window', 'Binary search', 'Running best / running total', 'Direct iteration / brute force'
TECHNIQUES = [BRUTE, HASH, POINTERS, WINDOW, SEARCH, RUNNING]

PARTNER = (r'target\s*[-−]|complement|partner|\bneed|differen|remain|missing', 'the value that completes a pair with the current one', 'For the current value, which exact value would complete the pair?')
MIDDLE = (r'middle|\bmid\b|half|halv', 'comparing with the middle of the remaining range', 'Which position do you inspect first, and why that one?')
ENDS = (r'\bends?\b|both sides|first and last|opposite|left and right|outside|front and back', 'starting from the two ends', 'Which two positions do you compare first?')
COUNTS = (r'count|frequen|how many|occurrence|tally', 'tracking how many times each value occurs', 'Is knowing that a value appeared enough, or do you need how many times?')
CONTIGUOUS = (r'contiguous|consecutive|continuous|adjacent|window|in a row', 'only contiguous groups are candidates', 'Which elements are allowed to form a group?')
SLIDE = (r'(add|plus)[^.]{0,40}(remov|subtract|minus|drop)|(remov|subtract|minus|drop)[^.]{0,40}(add|plus)|enter|leav|incoming|outgoing|i\s*[-−]\s*k', 'adding the value that enters and removing the one that leaves', 'When the group moves by one position, which value enters and which leaves?')
REUSE = (r'overlap|share|reuse|previous (sum|total|window)|k\s*[-−]\s*1|running|keep (the|a) (sum|total)', 'reusing the overlap between neighbouring groups', 'What do two neighbouring groups have in common?')

APPROACHES = {
    'two-sum': (HASH, 'For each value x, find whether target − x appeared earlier and, if so, where.', 'A dictionary from value to earlier position answers that with one expected O(1) lookup instead of rescanning earlier elements.',
                {POINTERS: ('alternative', 'Sorting (value, index) pairs and moving two pointers also works, but costs O(n log n) and extra bookkeeping to recover the original positions.'), SEARCH: ('alternative', 'After sorting (value, index) pairs, binary search can find each partner in O(log n): O(n log n) overall.')},
                [PARTNER, (r'index|indices|position|map|dict|store|remember|save|record|seen', 'remembering earlier values together with their positions', 'What must you remember about earlier values so that you can return a position later?'),
                 (r'(check|look|search|find)[^.]{0,50}before[^.]{0,50}(stor|add|insert|sav|record|put)|(stor|add|insert|sav|record|put)[^.]{0,50}after', 'looking for the partner before storing the current value', 'Should the current value be stored before or after you look for its partner? Try [3, 3] with target 6.')]),
    'contains-duplicate': (HASH, 'For each value, check whether it already appeared.', 'A set of values seen so far answers membership in expected O(1), so one pass replaces comparing every pair.',
                {POINTERS: ('alternative', 'Sorting first puts duplicates next to each other, so comparing neighbours works in O(n log n).')},
                [(r'seen|\bset\b|remember|stor|record|visited|already|earlier|previous', 'remembering the values already processed', 'What do you need to remember about the values you have already passed?'),
                 (r'\bin\b|contain|exist|membership|look ?up|check', 'asking whether the current value is already remembered', 'Which question do you ask about the current value, and how quickly can you answer it?'),
                 (r'return true|stop|early|as soon|immediately|first (repeat|duplicate)', 'stopping at the first repeat', 'Once one repeat is found, do you still need to process the rest of the list?')]),
    'pair-count': (HASH, 'For each value x, find how many earlier values equal target − x.', 'A dictionary from value to frequency so far lets each new value add all of its earlier partners at once.', {},
                [PARTNER, COUNTS, (r'(add|count|total|sum)[^.]{0,50}before[^.]{0,50}(increment|stor|add|updat|record)|(increment|stor|updat|record)[^.]{0,50}after', 'counting partners before recording the current value', 'Should the current value be recorded before or after you add its partners? Try [3, 3, 3] with target 6.')]),
    'frequency-map': (HASH, 'For each value, update how many times it has appeared.', 'A dictionary from value to count keeps every total, so each occurrence costs one update instead of a rescan.', {},
                [(r'\bkey|\bmap\b|dict|each (value|number)|value\s*(→|->|to)', 'using each value as a key', 'What is the key in your table, and what is stored with it?'),
                 (r'\b0\b|zero|first time|not (yet )?(seen|present|in)|default|get\(', 'starting a new value at zero', 'What should happen the first time a value appears?'),
                 (r'increment|\+\s*1|add one|plus one|\+=|one pass|single pass|updat', 'updating the count in one pass', 'How does each new occurrence change the stored count?')]),
    'unique-values': (HASH, 'For each value, check whether it was already added to the output.', 'A set of added values answers that membership question in expected O(1); searching the growing output list does not.', {},
                [(r'seen|\bset\b|remember|stor|record|already|visited', 'remembering which values were already added', 'What do you need to remember about the values already in your output?'),
                 (r'not in|check|look ?up|contain|membership', 'checking membership before adding', 'Which check decides whether the current value goes into the output?'),
                 (r'result|output|list|append|answer', 'building the output list alongside the set', 'Which collection holds the values you return, and when does a value go there?')]),
    'intersection': (HASH, 'For each value of one array, check whether the other array contains it and whether it was already reported.', 'A set built from one array answers membership in expected O(1); removing a value after reporting it prevents repeats.',
                {POINTERS: ('alternative', 'Sorting both arrays and walking them together works in O(n log n + m log m).')},
                [(r'\bset\b|remember|stor|\bmap\b|dict|seen|first (array|list)|available', 'storing one array for fast checks', 'Which input would you store so that the other one can be checked quickly?'),
                 (r'\bin\b|check|look ?up|contain|exist|both|common|shared', 'checking each value against the stored array', 'For each value of one array, which question do you ask about the other?'),
                 (r'remov|delet|discard|once|duplicate|already (added|reported|output)|repeat', 'reporting each shared value only once', 'How do you stop a shared value from appearing twice in the result?')]),
    'first-unique': (HASH, 'Know each character\'s total count, then find the first position whose count is one.', 'A dictionary of counts is built in one pass; a second pass in the original order finds the first count of one.', {},
                [COUNTS, (r'second (pass|scan|loop)|two pass|again|then (scan|loop|go|iterate|check)|another (pass|loop)', 'a second pass after counting', 'After counting, how do you find the answer — what do you scan?'),
                 (r'order|left to right|from the start|original|position|index', 'scanning in the original order', 'Why must the final scan follow the string rather than the table?')]),
    'valid-anagram': (HASH, 'Compare how many times each character occurs in the two strings.', 'A dictionary of counts from one string can be consumed by the other; a missing or exhausted character proves they differ.', {},
                [(r'length|len\(|size', 'rejecting different lengths early', 'Which quick check rules out many non-anagrams immediately?'), COUNTS,
                 (r'decrement|subtract|minus|-=|decreas|consum|cancel|reduc|negative|compare (the )?counts|equal counts|same counts', 'checking the second string against the counts', 'How will you use the second string against the first string\'s counts?')]),
    'palindrome': (POINTERS, 'Compare the characters at both ends, then move both positions inward.', 'Two pointers from opposite ends compare each mirrored pair once and use O(1) extra space.', {},
                [ENDS, (r'inward|toward|middle|cent(er|re)|move (both|left|right)|left\s*\+=|right\s*-=|shrink', 'moving both positions inward', 'After a matching pair, which positions do you compare next?'),
                 (r'meet|cross|left\s*<\s*right|until|stop|mismatch|differ|return false', 'stopping on a mismatch or when the positions meet', 'When can you stop — on a mismatch, and when the positions meet?')]),
    'reverse-string': (POINTERS, 'Exchange the characters at mirrored positions, moving inward.', 'Two pointers at opposite ends swap each mirrored pair once; a list of characters makes the swaps possible.', {},
                [ENDS, (r'swap|exchang|switch|trade', 'swapping the mirrored characters', 'What happens to the two characters at your positions?'),
                 (r'\blist\b|array|join|mutable|immutable|characters', 'working on a mutable list of characters', 'Strings cannot be changed at an index. What could you work on instead?')]),
    'move-zeroes': (POINTERS, 'Keep the position where the next nonzero value belongs, and move each nonzero value there.', 'A read pointer scans while a write pointer marks the next slot, so values move in one pass, in place and in order.', {},
                [(r'write|next (position|slot|spot|place)|insert position|\bleft\b|slot|boundary', 'a position for the next nonzero value', 'Where should the next nonzero value go?'),
                 (r'non.?zero|not zero|!= ?0|only (when|if|for)', 'advancing that position only for nonzero values', 'Which values cause your write position to move?'),
                 (r'swap|exchang|order|relative|stable|in.place', 'keeping nonzero values in order, in place', 'How do you keep the nonzero values in their original order while moving them?')]),
    'remove-duplicates': (POINTERS, 'Compare each value with the last value you kept.', 'Because the input is sorted, duplicates are adjacent; a write pointer builds the unique prefix in one pass.',
                {HASH: ('alternative', 'A set of seen values also works, but it uses O(n) extra memory and ignores the sorted order that makes neighbour comparison enough.')},
                [(r'sorted|adjacent|next to|neighbo|consecutive|together', 'sorted order puts equal values together', 'What does sorted order guarantee about equal values?'),
                 (r'last (kept|retained|unique|written|added)|previous|prior|compare with', 'comparing with the last kept value', 'Which value should the current one be compared with?'),
                 (r'write|prefix|slice|\bleft\b|in.place', 'a write position for the unique prefix', 'Where does each new distinct value go, and which part do you return?')]),
    'sorted-squares': (POINTERS, 'Repeatedly pick the larger absolute value from the two ends.', 'In sorted input the largest squares sit at the ends, so two pointers fill the result from the back in one pass.', {},
                [(r'negative|absolute|abs\(|sign', 'negative values can have large squares', 'Why can a negative number produce the largest square?'), ENDS,
                 (r'back|from the (right|end)|revers|largest first|descending|right to left|last position', 'filling the result from the back', 'In which order do the two ends produce squares, and where should each square go?')]),
    'merge-sorted': (POINTERS, 'Repeatedly take the smaller of the two unconsumed front values.', 'One pointer per list walks each list once, reusing the order both inputs already have.', {},
                [(r'two (index|indices|pointers?|positions?)|each (list|array)|i and j|both (lists|arrays)', 'one position per list', 'How do you keep track of your place in each list?'),
                 (r'smaller|smallest|\bmin|compare|front|<=|less', 'taking the smaller front value', 'Which value must come next in the merged output?'),
                 (r'leftover|remaining|\brest\b|remainder|tail|run out|exhaust', 'appending what remains', 'What happens when one list runs out?')]),
    'two-sum-sorted': (POINTERS, 'Adjust the pair sum up or down by moving one end.', 'Sorted order means moving left can only increase the sum and moving right can only decrease it, so each move safely discards candidates.',
                {HASH: ('alternative', 'A value → index map still works in O(n) time, but it uses O(n) memory and ignores the sorted order this problem gives you.'), SEARCH: ('alternative', 'Binary-searching each value\'s partner works in O(n log n); two pointers use the order in O(n).')},
                [ENDS, (r'too small|less than|smaller|too (big|large)|greater|bigger|compare (the )?sum|sum\s*[<>]', 'letting the sum decide which end moves', 'How does the sum, compared with target, decide which position moves?'),
                 (r'sorted|order|increas|eliminat|rule out|discard', 'why a move safely discards candidates', 'Why is it safe to discard candidates when a position moves?')]),
    'binary-search': (SEARCH, 'Compare the target with the middle of the remaining range and discard the half that cannot contain it.', 'Sorted order lets one comparison rule out half the range, giving O(log n) steps.', {},
                [MIDDLE, (r'discard|eliminat|rule out|ignore|half|narrow|shrink|left\s*=|right\s*=', 'discarding the half that cannot contain the target', 'After comparing, which part of the range cannot contain the target?'),
                 (r'<=|cross|empty|until|boundar|inclusive|-1|not found', 'when the search stops', 'When does the search stop, and how do the boundaries make progress?')]),
    'search-insert': (SEARCH, 'Find the first position whose value is at least target.', 'That condition is false, then true across sorted input, so binary search can halve the range around the boundary.', {},
                [MIDDLE, (r'>=|at least|not less|lower bound|first (value|position|element|index)|insert', 'looking for the first value at least target', 'Which position are you really looking for when the target is absent?'),
                 (r'len\(|length|end of|after the last|keep mid|candidate|answer', 'allowing the end of the array as an answer', 'Why can the answer be len(nums), and how do you keep a possible answer in range?')]),
    'first-occurrence': (SEARCH, 'Find a match, record it, and keep searching to the left for an earlier one.', 'Binary search still halves the range; saving a candidate before moving left keeps the answer while you look for an earlier copy.', {},
                [MIDDLE, (r'(keep|continue)[^.]{0,30}(left|search)|go left|move left|earlier|right\s*=\s*mid', 'continuing left after a match', 'When you find the target, are you done? Which side might hold an earlier match?'),
                 (r'save|record|remember|stor|answer|candidate|result', 'saving a candidate before moving on', 'How do you avoid losing a match while you keep searching?')]),
    'last-occurrence': (SEARCH, 'Find a match, record it, and keep searching to the right for a later one.', 'Binary search still halves the range; saving a candidate before moving right keeps the answer while you look for a later copy.', {},
                [MIDDLE, (r'(keep|continue)[^.]{0,30}(right|search)|go right|move right|later|left\s*=\s*mid', 'continuing right after a match', 'When you find the target, are you done? Which side might hold a later match?'),
                 (r'save|record|remember|stor|answer|candidate|result', 'saving a candidate before moving on', 'How do you avoid losing a match while you keep searching?')]),
    'max-window-sum': (WINDOW, 'Update the current group\'s sum as one value enters and one leaves.', 'A sliding window reuses the previous sum — add nums[i], subtract nums[i − k] — instead of adding k values again.',
                {RUNNING: ('partial', 'A running total is part of it, and prefix sums work, but a window also removes the value that leaves: total += nums[i] − nums[i − k].')},
                [CONTIGUOUS, REUSE, SLIDE]),
    'average-window': (WINDOW, 'Update the current group\'s sum as one value enters and one leaves, then divide by k.', 'Every window has the same divisor, so the largest sum gives the largest average; the window sum updates in O(1).',
                {RUNNING: ('partial', 'A running total is part of it, and prefix sums work, but a window also removes the value that leaves: total += nums[i] − nums[i − k].')},
                [CONTIGUOUS, REUSE, SLIDE]),
    'longest-unique': (WINDOW, 'Extend the range to the right and, on a repeat, move the left edge just past the earlier copy.', 'A variable sliding window with a map of last positions keeps the range valid while each edge only moves forward.',
                {HASH: ('partial', 'A map of last positions is half of the approach. The other half is a window whose left edge jumps past a repeat and never moves backwards.'), POINTERS: ('partial', 'Two moving edges are right. What makes it a sliding window is the validity rule — no repeats inside — and how the left edge restores it.')},
                [(r'window|range|substring|contiguous|left and right|two (pointers|indices)', 'a range with a left and right edge', 'Which range are you tracking, and what makes it valid?'),
                 (r'last (position|index|seen|occurrence)|position|index|\bmap\b|dict|seen', 'remembering where each character last appeared', 'What do you need to remember about each character to repair a repeat quickly?'),
                 (r'(move|jump|shift|advance)[^.]{0,30}left|left[^.]{0,30}(move|jump|shift|advance)|never (move|go)s? back|only (moves )?forward|>=\s*left|past the (repeat|previous|earlier)', 'moving the left edge forward past a repeat', 'When a repeat appears, where does the left edge go, and can it ever move backwards?')]),
    'best-profit': (RUNNING, 'For each day, know the lowest earlier price.', 'Carrying the running minimum turns each day\'s best sale into one subtraction, in one pass.',
                {POINTERS: ('alternative', 'A buy index and a sell index work if the buy index jumps to every new lower price — the running minimum in another form.'), WINDOW: ('alternative', 'Treating buy..sell as a window works when its left edge jumps to each new minimum — the same running-minimum idea.')},
                [(r'before|earlier|after|later|chronolog|order|past', 'buying before selling', 'Which prices can be paired with today\'s price?'),
                 (r'\bmin|lowest|cheapest|smallest', 'tracking the lowest earlier price', 'For today\'s sale, which earlier price matters?'),
                 (r'best|\bmax|largest|so far|updat', 'updating the best profit while scanning', 'How do you keep the best answer as you scan?')]),
    'max-subarray': (RUNNING, 'For each position, decide whether to extend the best range ending at the previous position or start fresh.', 'Carrying the best sum ending here, and the best overall, drops a negative prefix as soon as it would hurt.',
                {WINDOW: ('partial', 'A window that restarts is close. The rule that decides the restart — drop the range when its sum is negative — is the running-best idea.')},
                [(r'ending (here|at)|current|extend|continu|start (fresh|over|new)|restart', 'the best range ending at each position', 'For each position, what are your two choices for a range ending there?'),
                 (r'negative|below zero|<\s*0|drop|reset|discard|throw away', 'dropping a prefix that hurts', 'When does carrying the previous range hurt?'),
                 (r'best|\bmax|overall|global|so far', 'keeping the best overall separately', 'How do you keep the best range seen anywhere, separate from the current one?')]),
}

# ----------------------------------------------------------------------------
# Changed requirements. Same parameters and input rules, a different output contract
# that the original approach cannot satisfy unchanged (tests/test_curriculum.py proves it).
# ----------------------------------------------------------------------------
MODIFICATIONS = {
    'two-sum': ('Count every pair', 'Now return how many index pairs i < j add up to target. Equal values at different positions count separately.', 'Return an integer count.',
        'One saved position per value was enough to report a pair. Is it enough to count every pair?', 'A value can partner with several earlier positions. Store how many times each value has appeared, not where.',
        'Counting changes what is worth remembering: a single position per value loses earlier partners, while a frequency lets each new value add all of them at once.',
        '''counts = {}
total = 0
for x in nums:
    total += counts.get(target - x, 0)
    counts[x] = counts.get(x, 0) + 1
return total''', [('Example', [[2, 7, 11, 15], 9], 1), ('Three equal values', [[3, 3, 3], 6], 3), ('No pair', [[1, 2, 4], 8], 0), ('Repeated partners', [[1, 1, 2, 2], 3], 4)]),
    'contains-duplicate': ('Three of a kind', 'Now return True only if some value appears at least three times.', 'Return True or False.',
        'Membership was enough to detect a second copy. What do you need to know to detect a third?', 'Track how many times each value has appeared so far, and stop when a count reaches three.',
        'A set can only answer "seen before?". Detecting a third copy needs a count per value — the same one-pass shape with richer memory.',
        '''counts = {}
for x in nums:
    counts[x] = counts.get(x, 0) + 1
    if counts[x] == 3:
        return True
return False''', [('Example', [[1, 2, 1, 1]], True), ('Only two copies', [[1, 2, 1]], False), ('Empty', [[]], False), ('Two pairs', [[1, 1, 2, 2]], False), ('All equal', [[5, 5, 5]], True)]),
    'pair-count': ('Each position once', 'Now each position may belong to at most one pair. Return the largest number of disjoint pairs that add up to target.', 'Return an integer count.',
        'Before, one value could pair with every earlier partner. What must happen to a partner once it is used?', 'When the current value finds an unused partner, consume one of that partner\'s copies instead of recording the current value.',
        'Disjoint pairs turn the frequency table into a pool of unused values: a match consumes a partner, and only unmatched values are added.',
        '''unused = {}
pairs = 0
for x in nums:
    if unused.get(target - x, 0) > 0:
        unused[target - x] -= 1
        pairs += 1
    else:
        unused[x] = unused.get(x, 0) + 1
return pairs''', [('Example', [[1, 1, 2, 2], 3], 2), ('Odd count of equal values', [[3, 3, 3], 6], 1), ('No pair', [[2, 5], 9], 0), ('Empty', [[], 4], 0), ('Mixed', [[1, 2, 3, 2, 1, 4], 4], 2)]),
    'frequency-map': ('Only the highest count', 'Now return only the highest count: how many times the most frequent value appears. Return 0 for an empty list.', 'Return an integer.',
        'You no longer return the whole table. What must you track while counting?', 'Keep a running best alongside the counts and update it after each increment.',
        'The counting stays the same; the output contract adds a running best, so the answer is ready at the end of the single pass.',
        '''counts = {}
best = 0
for x in nums:
    counts[x] = counts.get(x, 0) + 1
    best = max(best, counts[x])
return best''', [('Example', [[2, 7, 2, 4, 7, 2]], 3), ('Empty', [[]], 0), ('One value', [[9]], 1), ('Tie', [[1, 2, 1, 2]], 2)]),
    'unique-values': ('Values seen exactly once', 'Now return only the values that occur exactly once, in their original order.', 'Return a list in input order.',
        '"Already seen" was enough to skip repeats. Is it enough to know a value never repeats later?', 'You cannot decide while scanning forward. Count everything first, then scan the input in order.',
        'Exactly-once depends on the whole input, so the decision moves after a full count, and order now matters in the final scan.',
        '''counts = {}
for x in nums:
    counts[x] = counts.get(x, 0) + 1
result = []
for x in nums:
    if counts[x] == 1:
        result.append(x)
return result''', [('Example', [[2, 2, 7, 4, 7]], [4]), ('Empty', [[]], []), ('All repeated', [[5, 5, 5]], []), ('All distinct', [[1, 2, 3]], [1, 2, 3]), ('Order matters', [[3, 1, 3, 2]], [1, 2])]),
    'intersection': ('Keep shared repeats', 'Now keep repeats: each shared value appears as many times as it occurs in both arrays (the smaller count), in the order it appears in other.', 'Return a list.',
        'Removing a value after one match prevented repeats. What should be remembered instead, so repeats are allowed but limited?', 'Store how many copies of each value nums still has available, and use one copy per match.',
        'Membership became multiplicity: a count of available copies limits repeats exactly, where a set could only allow one.',
        '''available = {}
for x in nums:
    available[x] = available.get(x, 0) + 1
result = []
for x in other:
    if available.get(x, 0) > 0:
        result.append(x)
        available[x] -= 1
return result''', [('Example', [[1, 2, 2, 4], [2, 2, 3]], [2, 2]), ('No overlap', [[1], [2]], []), ('Empty input', [[], [3]], []), ('Order of other', [[1, 2, 3], [3, 1]], [3, 1]), ('Smaller count wins', [[4, 4, 4], [4, 4]], [4, 4])]),
    'first-unique': ('The first repeat', 'Now return the first character whose second occurrence comes earliest while reading left to right. Return "" if no character repeats.', 'Return a one-character string, or "".',
        'Uniqueness needed the full count first. Does finding the first repeat?', 'Read left to right and remember characters you have passed; the first one you meet again is the answer.',
        'The answer is now decided at the moment of the repeat, so one forward pass with a set of seen characters replaces counting the whole string.',
        '''seen = set()
for ch in text:
    if ch in seen:
        return ch
    seen.add(ch)
return ""''', [('Example', ['abcab'], 'a'), ('Longer word', ['loveleetcode'], 'l'), ('No repeat', ['abc'], ''), ('Empty', [''], ''), ('Inner repeat', ['abba'], 'b')]),
    'valid-anagram': ('How many changes?', 'Now return how many characters of other must be replaced to make it an anagram of text. Return -1 if the lengths differ.', 'Return an integer.',
        'A yes/no answer could stop at the first missing character. What must you count instead?', 'Consume text\'s counts with other; every character with no count left must be replaced.',
        'The same count table now measures distance instead of equality: each unmatched character in other is one required replacement.',
        '''if len(text) != len(other):
    return -1
counts = {}
for ch in text:
    counts[ch] = counts.get(ch, 0) + 1
changes = 0
for ch in other:
    if counts.get(ch, 0) > 0:
        counts[ch] -= 1
    else:
        changes += 1
return changes''', [('Example', ['anagram', 'nagaram'], 0), ('One change', ['aab', 'abb'], 1), ('Different lengths', ['ab', 'abc'], -1), ('Both empty', ['', ''], 0), ('Nothing shared', ['abc', 'xyz'], 3)]),
    'palindrome': ('One deletion allowed', 'Now return True if text reads the same forwards and backwards after deleting at most one character.', 'Return True or False.',
        'Before, the first mismatch ended the check. Which possibilities remain after one mismatch now — and why only those?', 'At the first mismatch, either the left or the right character is the one to delete. Check each remaining range once.',
        'The two-pointer scan stays; a mismatch now branches into exactly two inner ranges, each checked with the same inward scan.',
        '''left = 0
right = len(text) - 1
while left < right and text[left] == text[right]:
    left += 1
    right -= 1
i = left + 1
j = right
while i < j and text[i] == text[j]:
    i += 1
    j -= 1
if i >= j:
    return True
i = left
j = right - 1
while i < j and text[i] == text[j]:
    i += 1
    j -= 1
return i >= j''', [('Example', ['abca'], True), ('Already a palindrome', ['racecar'], True), ('Two deletions needed', ['abc'], False), ('Empty', [''], True), ('Delete the first', ['deeee'], True), ('Neither side works', ['abccbx'], False)]),
    'reverse-string': ('Letters only', 'Now reverse only the letters. Every other character — spaces, digits, punctuation — stays at its position.', 'Return the new string.',
        'Every mirrored pair was swapped before. What should happen when one of the two positions is not a letter?', 'Move a pointer past a non-letter without swapping; swap only when both positions hold letters.',
        'The pointers still meet in the middle, but each one now skips positions the requirement fixes in place.',
        '''chars = list(text)
left = 0
right = len(chars) - 1
while left < right:
    if not chars[left].isalpha():
        left += 1
    elif not chars[right].isalpha():
        right -= 1
    else:
        chars[left], chars[right] = chars[right], chars[left]
        left += 1
        right -= 1
return "".join(chars)''', [('Example', ['ab-c'], 'cb-a'), ('Space stays', ['a b'], 'b a'), ('Empty', [''], ''), ('Digits stay', ['1x2y'], '1y2x'), ('Only letters', ['hello'], 'olleh')]),
    'move-zeroes': ('Zeroes to the front', 'Now move every zero to the front, keeping the nonzero values in their original order. Modify the list in place before returning it.', 'Return the modified array.',
        'Your write position grew from the left. Where should it start now, and which way should the scan go?', 'Fill nonzero values from the right end, scanning from right to left.',
        'Mirroring the requirement mirrors the pointers: the write position starts at the end and the scan runs backwards, preserving order.',
        '''write = len(nums) - 1
for i in range(len(nums) - 1, -1, -1):
    if nums[i] != 0:
        nums[write], nums[i] = nums[i], nums[write]
        write -= 1
return nums''', [('Example', [[0, 1, 0, 3, 12]], [0, 0, 1, 3, 12]), ('All zeroes', [[0, 0]], [0, 0]), ('No zeroes', [[1, 2]], [1, 2]), ('Empty', [[]], []), ('Zero in the middle', [[4, 0, 5]], [0, 4, 5])]),
    'remove-duplicates': ('At most two copies', 'The input is still sorted. Now keep at most two copies of each value and return the resulting list.', 'Return a sorted list.',
        'You compared with the last kept value. Which kept value tells you whether a third copy is coming?', 'Compare the current value with the value kept two positions back in your output.',
        'The invariant generalises: the kept prefix allows a value only if it differs from the element two slots back.',
        '''left = 0
for i in range(len(nums)):
    if left < 2 or nums[i] != nums[left - 2]:
        nums[left] = nums[i]
        left += 1
return nums[:left]''', [('Example', [[1, 1, 1, 2, 2, 3]], [1, 1, 2, 2, 3]), ('Empty', [[]], []), ('All same', [[2, 2, 2]], [2, 2]), ('Distinct', [[1, 3, 5]], [1, 3, 5]), ('Long run', [[0, 0, 1, 1, 1, 1, 2]], [0, 0, 1, 1, 2])]),
    'sorted-squares': ('Count distinct squares', 'The input is still sorted. Now return how many distinct values the squares take.', 'Return an integer count.',
        'Your two pointers produced squares in a particular order. How does that order help you notice repeats?', 'The ends produce squares from largest to smallest, so equal squares arrive next to each other. Compare with the last one.',
        'The two-pointer order is itself the tool: it yields squares in nonincreasing order, so counting distinct values needs only the previous square.',
        '''left = 0
right = len(nums) - 1
count = 0
last = -1
while left <= right:
    if abs(nums[left]) > abs(nums[right]):
        value = abs(nums[left])
        left += 1
    else:
        value = abs(nums[right])
        right -= 1
    if value != last:
        count += 1
        last = value
return count''', [('Example', [[-4, -1, 0, 3, 10]], 5), ('Mirror values', [[-2, 2]], 1), ('Two pairs', [[-3, -1, 1, 3]], 2), ('Empty', [[]], 0), ('Zeroes', [[0, 0]], 1)]),
    'merge-sorted': ('Merge without repeats', 'Both arrays are still sorted. Now return the merged sorted array with each value at most once.', 'Return a sorted list without repeats.',
        'The merge produced values in order. Where would a repeat show up, and what do you compare it with?', 'Values arrive in order, so a repeat always equals the last value you appended.',
        'Sorted output makes duplicates adjacent, so the merge needs one extra comparison against its own last output.',
        '''i = 0
j = 0
result = []
while i < len(nums) or j < len(other):
    if j == len(other) or (i < len(nums) and nums[i] <= other[j]):
        value = nums[i]
        i += 1
    else:
        value = other[j]
        j += 1
    if len(result) == 0 or result[-1] != value:
        result.append(value)
return result''', [('Example', [[1, 2, 3], [2, 3, 4]], [1, 2, 3, 4]), ('Same value', [[1, 1], [1]], [1]), ('Both empty', [[], []], []), ('Repeats in one list', [[], [1, 1, 2]], [1, 2]), ('Disjoint', [[1, 3, 5], [2, 4, 6]], [1, 2, 3, 4, 5, 6])]),
    'two-sum-sorted': ('Closest pair sum', 'The array is still sorted. Now return the pair sum (two different positions) closest to target; if two sums are equally close, return the smaller one. Return None with fewer than two numbers.', 'Return an integer sum, or None.',
        'An exact match may not exist. The pointers can still move the same way — what must you remember as they move?', 'Keep the best sum seen so far, and keep moving the pointer that brings the sum toward target.',
        'The pointer moves stay valid because they still discard only sums that are farther on the same side; the new requirement adds a running best.',
        '''if len(nums) < 2:
    return None
left = 0
right = len(nums) - 1
best = nums[0] + nums[1]
while left < right:
    total = nums[left] + nums[right]
    if abs(total - target) < abs(best - target) or (abs(total - target) == abs(best - target) and total < best):
        best = total
    if total == target:
        return total
    if total < target:
        left += 1
    else:
        right -= 1
return best''', [('Example', [[2, 7, 11, 15], 18], 18), ('No exact pair', [[1, 2, 4], 8], 6), ('Far target', [[1, 3], 10], 4), ('Tie goes smaller', [[-5, -1, 3, 8], 0], -2), ('Too short', [[1], 5], None)]),
    'binary-search': ('Count occurrences', 'The array is still sorted. Now return how many times target appears.', 'Return an integer count.',
        'Any match was enough before. Which two boundaries determine the count?', 'Find the first position with a value ≥ target and the first with a value > target; the count is their difference.',
        'Counting asks for boundaries rather than a match: two binary searches find them in O(log n) instead of scanning the run of equal values.',
        '''left = 0
right = len(nums)
while left < right:
    mid = (left + right) // 2
    if nums[mid] < target:
        left = mid + 1
    else:
        right = mid
start = left
right = len(nums)
while left < right:
    mid = (left + right) // 2
    if nums[mid] <= target:
        left = mid + 1
    else:
        right = mid
return left - start''', [('Example', [[1, 2, 2, 2, 4], 2], 3), ('Absent', [[1, 3, 5], 4], 0), ('Empty', [[], 7], 0), ('All equal', [[2, 2, 2], 2], 3), ('Single copy', [[1, 3, 5, 7, 9, 11, 13], 9], 1)]),
    'search-insert': ('Insert after equals', 'Now return the last position where target could be inserted while keeping the order — after any values equal to target.', 'Return an index from 0 to len(nums).',
        'Which single comparison decided whether an equal value stays to the right of your answer?', 'An equal value must now stay to the left of the answer: move left past it.',
        'The boundary moved from "first value ≥ target" to "first value > target"; one comparison operator encodes which side equal values belong to.',
        '''left = 0
right = len(nums)
while left < right:
    mid = (left + right) // 2
    if nums[mid] <= target:
        left = mid + 1
    else:
        right = mid
return left''', [('Example', [[1, 3, 3, 5], 3], 3), ('Absent', [[1, 3, 5, 6], 2], 1), ('After the end', [[1, 3], 8], 2), ('Empty', [[], 4], 0), ('All equal', [[2, 2, 2], 2], 3)]),
    'first-occurrence': ('First value greater than target', 'Now return the first index whose value is greater than target, or -1 if no value is.', 'Return an index, or -1.',
        'The target no longer needs to exist. Which condition defines a candidate now, and which way do you keep searching?', 'Every value greater than target is a candidate; save it and keep looking left for an earlier one.',
        'The search keeps its shape — save a candidate, keep halving toward earlier positions — while the candidate condition changes from equality to greater-than.',
        '''left = 0
right = len(nums) - 1
answer = -1
while left <= right:
    mid = (left + right) // 2
    if nums[mid] > target:
        answer = mid
        right = mid - 1
    else:
        left = mid + 1
return answer''', [('Example', [[1, 2, 2, 2, 4], 2], 4), ('Absent target', [[1, 3], 2], 1), ('Empty', [[], 1], -1), ('Nothing greater', [[2, 2, 2], 2], -1), ('All greater', [[5, 6], 1], 0)]),
    'last-occurrence': ('Last value smaller than target', 'Now return the last index whose value is smaller than target, or -1 if no value is.', 'Return an index, or -1.',
        'The target no longer needs to exist. Which condition defines a candidate now, and which way do you keep searching?', 'Every value smaller than target is a candidate; save it and keep looking right for a later one.',
        'The search keeps its shape — save a candidate, keep halving toward later positions — while the candidate condition changes from equality to less-than.',
        '''left = 0
right = len(nums) - 1
answer = -1
while left <= right:
    mid = (left + right) // 2
    if nums[mid] < target:
        answer = mid
        left = mid + 1
    else:
        right = mid - 1
return answer''', [('Example', [[1, 2, 2, 2, 4], 2], 0), ('Absent target', [[1, 3], 2], 0), ('Empty', [[], 1], -1), ('Nothing smaller', [[2, 2, 2], 2], -1), ('All smaller', [[1, 2, 3], 9], 2)]),
    'max-window-sum': ('Where is the best window?', 'Now return the starting index of the window of size k with the largest sum. If several windows tie, return the earliest.', 'Return a starting index.',
        'The best sum was enough before. What else must you remember when the best changes, and when should a tie replace it?', 'Record the window\'s start whenever the sum strictly improves; the start of the window ending at i is i − k + 1.',
        'The window update is unchanged; the output needs the position of the best window, and a strict comparison keeps the earliest tie.',
        '''total = sum(nums[:k])
best = total
start = 0
for i in range(k, len(nums)):
    total += nums[i] - nums[i - k]
    if total > best:
        best = total
        start = i - k + 1
return start''', [('Example', [[2, 1, 5, 1, 3, 2], 3], 2), ('Negative values', [[-4, -2, -1], 2], 1), ('Whole array', [[2, 3], 2], 0), ('One item window', [[1, 7, 2], 1], 1), ('Tie keeps earliest', [[3, 1, 3], 1], 0)]),
    'average-window': ('Windows that wrap', 'Now the array is circular: a window may continue from the end back to the start. Return the maximum average of k contiguous values.', 'Return a float.',
        'Your window stopped at the end of the array. Which windows are new, and how do you index them?', 'Keep sliding past the end and read positions with index % len(nums).',
        'Circularity adds k − 1 windows; the same add-one, remove-one update covers them once indices wrap with modulo.',
        '''n = len(nums)
total = sum(nums[:k])
best = total
for i in range(k, n + k - 1):
    total += nums[i % n] - nums[i - k]
    best = max(best, total)
return best / k''', [('Example', [[1, 12, -5, -6, 50, 3], 4], 16.5), ('Two values', [[2, 4], 2], 3.0), ('Negative', [[-3, -1], 1], -1.0), ('One value', [[8], 1], 8.0), ('Best window wraps', [[5, 1, 1, 5], 2], 5.0)]),
    'longest-unique': ('At most two of each', 'Now return the length of the longest substring in which no character appears more than twice.', 'Return the range length.',
        'Jumping past the previous copy worked when one copy was allowed. Where should the left edge go when a third copy appears?', 'Keep a count per character inside the window and shrink from the left until the new character\'s count is two again.',
        'Last positions only remember one copy, so the window now keeps counts and shrinks step by step until it is valid again.',
        '''counts = {}
left = 0
best = 0
for right, ch in enumerate(text):
    counts[ch] = counts.get(ch, 0) + 1
    while counts[ch] > 2:
        counts[text[left]] -= 1
        left += 1
    best = max(best, right - left + 1)
return best''', [('Example', ['abcabcbb'], 6), ('All same', ['bbbbb'], 2), ('Empty', [''], 0), ('Allowed repeat', ['abba'], 4), ('Third copy', ['aaabb'], 4)]),
    'best-profit': ('Many transactions', 'Now you may buy and sell as many times as you like, holding at most one share at a time. Return the largest total profit.', 'Return a nonnegative total.',
        'One lowest buy price summarised everything before. What does each price rise contribute now?', 'Every increase from one day to the next can be captured by its own buy and sell.',
        'With unlimited transactions the running minimum is no longer the summary; the total is the sum of every positive day-to-day change.',
        '''total = 0
for i in range(1, len(nums)):
    if nums[i] > nums[i - 1]:
        total += nums[i] - nums[i - 1]
return total''', [('Example', [[7, 1, 5, 3, 6, 4]], 7), ('Falling prices', [[7, 6, 4]], 0), ('Empty', [[]], 0), ('Rising', [[1, 2, 4]], 3), ('Two climbs', [[1, 5, 2, 6]], 8)]),
    'max-subarray': ('Largest product', 'Now return the largest product of a nonempty contiguous subarray. For empty input, return 0.', 'Return an integer product.',
        'A negative running sum was safe to drop. Can a negative running product become the best later?', 'Carry both the largest and the smallest product ending at each position; a negative number swaps their roles.',
        'Multiplication by a negative turns the worst range into the best, so the running state grows from one value to two.',
        '''if len(nums) == 0:
    return 0
high = nums[0]
low = nums[0]
best = nums[0]
for i in range(1, len(nums)):
    x = nums[i]
    candidates = [x, high * x, low * x]
    high = max(candidates)
    low = min(candidates)
    best = max(best, high)
return best''', [('Example', [[2, 3, -2, 4]], 6), ('Zero splits', [[-2, 0, -1]], 0), ('Two negatives', [[-2, 3, -4]], 24), ('Empty', [[]], 0), ('Single negative', [[-3]], -3)]),
}

for p in problems:
    technique, operation, why, alternatives, checkpoints = APPROACHES[p['id']]
    p['approach'] = {'technique': technique, 'operation': operation, 'why': why,
                     'alternatives': {name: {'kind': kind, 'note': note} for name, (kind, note) in alternatives.items()},
                     'checkpoints': [{'pattern': pattern, 'label': label, 'question': question} for pattern, label, question in checkpoints]}
    title, statement, returns, question, clue, insight, body, cases = MODIFICATIONS[p['id']]
    params = ', '.join(p['params'])
    p['modification'] = {'id': p['id'] + '-modified', 'title': title, 'statement': statement, 'returns': returns, 'question': question, 'clue': clue, 'insight': insight,
                         'solution': 'def solve(' + params + '):\n' + '\n'.join('    ' + line for line in body.strip().splitlines()) + '\n',
                         'example': {'args': cases[0][1], 'expected': cases[0][2]},
                         'tests': [{'name': name, 'args': inputs, 'expected': output} for name, inputs, output in cases]}

# The data-structure laboratories (linked lists to bits), authored with their approach and changed requirement.
from structures_curriculum import LABS  # noqa: E402
for lab in LABS:
    problems.append({'id': lab['id'], 'number': len(problems) + 1, **{k: v for k, v in lab.items() if k != 'id'}})

if __name__ == '__main__':
    destination = Path(__file__).with_name('problems.json')
    destination.write_text(json.dumps(problems, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Authored {len(problems)} problem laboratories: {destination}')
