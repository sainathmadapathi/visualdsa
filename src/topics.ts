/** Every topic the laboratory draws, in the homepage gallery's order; each has authored labs (`category` in the
 * curriculum is the topic's name). Rows of the learner's own sheets are matched to a topic by their sheet topic
 * ("Linked-List · Fundamentals") or, when the sheet gives none that fits, by their title. */
export type TopicColor = 'orange' | 'violet' | 'silver' | 'graphite';
export interface Topic { name: string; short: string; line: string; color: TopicColor; kind: string; drawn: string; match: RegExp }

export const TOPICS: Topic[] = [
  { name: 'Arrays', short: 'array', line: 'Every position tells a story.', color: 'orange', kind: 'array', drawn: 'indexed cells with pointers', match: /(?<!2d )\barrays?\b|subarray|prefix sums?/i },
  { name: 'Hash maps', short: 'hash-map', line: 'Find the connection. Skip the search.', color: 'violet', kind: 'map', drawn: 'keys and their values', match: /\bhash(ing|maps?|sets?)?\b|dictionar/i },
  { name: 'Two pointers', short: 'two-pointer', line: 'Two perspectives. One discovery.', color: 'silver', kind: 'pointer', drawn: 'two pointers moving through a list', match: /\b(two|2)[- ]?pointers?\b/i },
  { name: 'Sliding window', short: 'sliding-window', line: 'Move the frame. See the pattern.', color: 'orange', kind: 'window', drawn: 'a window over a list', match: /sliding[- ]window/i },
  { name: 'Binary search', short: 'binary-search', line: 'Less to search. More to understand.', color: 'graphite', kind: 'search', drawn: 'a range halving each step', match: /binary[- ]search(?![- ]trees?)/i },
  { name: 'Strings', short: 'string', line: 'Read it one character at a time.', color: 'violet', kind: 'string', drawn: 'characters with their indices', match: /\bstrings?\b|substring|palindrom|anagram/i },
  { name: 'Linked lists', short: 'linked-list', line: 'Follow the arrows. Rewire with care.', color: 'silver', kind: 'list', drawn: 'nodes and next pointers', match: /linked[- ]?lists?|\bd?ll\b/i },
  { name: 'Stacks', short: 'stack', line: 'The last thing in leads the way out.', color: 'orange', kind: 'stack', drawn: 'an upright stack', match: /\bstacks?\b/i },
  { name: 'Queues', short: 'queue', line: 'First come, first served, in order.', color: 'graphite', kind: 'queue', drawn: 'a queue from front to back', match: /\bqueues?\b|\bdeques?\b/i },
  { name: 'Heaps', short: 'heap', line: 'The smallest always rises to the top.', color: 'violet', kind: 'heap', drawn: 'a heap as a tree and an array', match: /\bheaps?\b|priority[- ]queue/i },
  { name: 'Recursion', short: 'recursion', line: 'Trust the smaller call. Watch it return.', color: 'silver', kind: 'recursion', drawn: 'a call tree with return values', match: /recursi|backtrack|subsequence/i },
  { name: 'Trees', short: 'tree', line: 'Every answer starts at the root.', color: 'orange', kind: 'tree', drawn: 'nodes laid out by depth', match: /(?<!spanning )\btrees?\b|\bbsts?\b/i },
  { name: 'Tries', short: 'trie', line: 'Words that share a beginning share a path.', color: 'graphite', kind: 'trie', drawn: 'a trie with letter edges', match: /\btries\b|\btrie\b|prefix tree/i },
  { name: 'Graphs', short: 'graph', line: 'Visit, mark, and move to the neighbours.', color: 'violet', kind: 'graph', drawn: 'a graph coloured by visited and queued', match: /\bgraphs?\b|shortest path|spanning tree|topolog|dijkstra|\bbfs\b|\bdfs\b|union[- ]find|disjoint set/i },
  { name: 'Grids & matrices', short: 'grid', line: 'Rows, columns and the cells between.', color: 'silver', kind: 'grid', drawn: 'a grid with row and column pointers', match: /matri(x|ces)|\bgrids?\b|2d arrays?/i },
  { name: 'Dynamic programming', short: 'DP', line: 'Solve it once. Remember it forever.', color: 'orange', kind: 'dp', drawn: 'a table filling cell by cell', match: /dynamic[- ]programming|\bdp\b|memoi[sz]|tabulation/i },
  { name: 'Bit manipulation', short: 'bit-manipulation', line: 'Thirty-two switches in every number.', color: 'graphite', kind: 'bits', drawn: 'each number bit by bit', match: /\bbits?\b|bitwise|\bxor\b/i },
];

export const topicNamed = (name: string) => TOPICS.find(t => t.name === name);

/** The topics a problem belongs to: by its sheet topic when that names one, otherwise by its title. */
export function topicsOf(topic: string, title: string) {
  const byTopic = TOPICS.filter(t => t.match.test(topic));
  return byTopic.length ? byTopic : TOPICS.filter(t => t.match.test(title));
}

export const inTopic = (name: string, topic: string, title: string) => topicsOf(topic, title).some(t => t.name === name);
