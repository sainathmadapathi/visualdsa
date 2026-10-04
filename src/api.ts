import { auth } from './firebase';

/** The lab's own address in development (npm run dev, which also starts the API). */
const LAB = 'localhost:5173';
/** Why nothing answers: the server behind this tab has stopped. When this tab is an old one on another local port
 * and the lab is running at its own address, say where it is instead. */
async function unreachable() {
  const local = ['localhost', '127.0.0.1'].includes(location.hostname);
  if (local && location.host !== LAB && location.port !== '5057') {  // 5057: the API serving the built app itself.
    try {
      await fetch(`http://${LAB}/`, { mode: 'no-cors', signal: AbortSignal.timeout(1500) });  // Resolves only if something answers there.
      return `Nothing is running at ${location.host} any more, but the lab is running at ${LAB}. Open http://${LAB} and continue there.`;
    } catch { /* Not running there either. */ }
  }
  return `The lab's server at ${location.host} has stopped. Start it again with "npm run dev" (it starts the learning API too), then try again.`;
}
/** Calls the Flask API. Success: the endpoint's JSON. Failure: an Error carrying the API's {error, details}. */
export async function api<T>(path: string, body?: unknown, method?: 'DELETE'): Promise<T> {
  const token = await auth?.currentUser?.getIdToken();
  // A FormData body (a file upload) sets its own multipart content type.
  const form = body instanceof FormData;
  let response: Response | null = null;
  // A refused connection never reached the server, so it is safe to try again: a restarting server gets a moment.
  for (const wait of [0, 700, 1500]) {
    if (wait) await new Promise(resolve => setTimeout(resolve, wait));
    try {
      response = await fetch('/api' + path, {
        method: method ?? (body === undefined ? 'GET' : 'POST'),
        headers: { ...(form ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
      });
      break;
    } catch { /* Nothing answered at this page's own address. */ }
  }
  if (!response) throw Object.assign(new Error(await unreachable()), { line: null });
  // The API always answers in JSON; anything else means the request never reached it, or it stopped mid-way.
  const text = await response.text();
  let data: { error?: string; details?: string; line?: number | null } | null = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok || data === null) {
    const message = data?.error
      || (!text && response.status >= 500 ? 'The learning API is not responding: it may not be running. Start it with "python app.py", then try again.'
        : `The server answered with status ${response.status} but no readable message.`);
    throw Object.assign(new Error(message), { line: data?.line ?? null, details: data?.details ?? null, status: response.status });
  }
  return data as T;
}
