import { auth } from './firebase';
/** Calls the Flask API. Success: the endpoint's JSON. Failure: an Error carrying the API's {error, details}. */
export async function api<T>(path: string, body?: unknown, method?: 'DELETE'): Promise<T> {
  const token = await auth?.currentUser?.getIdToken();
  // A FormData body (a file upload) sets its own multipart content type.
  const form = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch('/api' + path, {
      method: method ?? (body === undefined ? 'GET' : 'POST'),
      headers: { ...(form ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
    });
  } catch {
    // Nothing answered at this page's own address: the server that served this page has stopped.
    throw Object.assign(new Error(`The laboratory server at ${location.host} could not be reached. Check that it is running (or open the address it runs on), then try again.`), { line: null });
  }
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
