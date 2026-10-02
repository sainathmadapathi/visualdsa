import { auth } from './firebase';
export async function api<T>(path: string, body?: unknown, method?: 'DELETE'): Promise<T> {
  const token = await auth?.currentUser?.getIdToken();
  // A FormData body (a file upload) sets its own multipart content type.
  const form = body instanceof FormData;
  const response = await fetch('/api' + path, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: { ...(form ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || 'The request could not be completed.'), { line: data.line ?? null });
  return data;
}
