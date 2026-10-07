import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { connect } from 'node:net';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import type { Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// The API's own port, not Flask's usual 5000: another local project on 5000 would otherwise take its place.
const API_PORT = Number(process.env.LAB_API_PORT || 5057);
const ROOT = fileURLToPath(new URL('.', import.meta.url));
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/** Is something accepting connections on the API's port? */
const listening = () => new Promise<boolean>(resolve => {
  const socket = connect({ host: '127.0.0.1', port: API_PORT });
  const done = (up: boolean) => { socket.destroy(); resolve(up); };
  socket.once('connect', () => done(true));
  socket.once('error', () => done(false));
  socket.setTimeout(500, () => done(false));
});

/**
 * The lab is one app: starting the web server starts the Flask API with it (`python app.py`, exactly as by hand)
 * and keeps it there. An API already listening on its port is used as it is. A request made while the API is
 * starting waits for it instead of failing, and if the API has stopped, the next request starts it again.
 * Set LAB_API=external to manage the API yourself; LAB_PYTHON picks the Python to run it with.
 */
function labApi(): Plugin {
  let child: ChildProcess | null = null;
  let pending: Promise<boolean> | null = null;
  let lastStart = 0;
  const output: string[] = [];
  const partial = { out: '', err: '' };
  // Output arrives in chunks that can split a line: print whole lines only, and not every request line.
  const keep = (stream: 'out' | 'err') => (chunk: Buffer) => {
    const lines = (partial[stream] + chunk.toString()).split(/\r?\n/);
    partial[stream] = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      output.push(line);
      if (!/"(GET|POST|PUT|DELETE) \S+ HTTP/.test(line)) console.log(`[api] ${line}`);
    }
    output.splice(0, Math.max(0, output.length - 30));
  };
  const start = async () => {
    if (await listening()) return true;
    if (!child || child.exitCode !== null || child.killed) {
      await sleep(Math.max(0, lastStart + 3000 - Date.now()));  // An API that keeps crashing is not restarted in a tight loop.
      if (await listening()) return true;
      lastStart = Date.now();
      output.length = 0;
      child = spawn(process.env.LAB_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), ['app.py'], { cwd: ROOT, env: { ...process.env, PORT: String(API_PORT) }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
      child.stdout?.on('data', keep('out'));
      child.stderr?.on('data', keep('err'));
      child.on('error', error => output.push(`Could not start the API: ${error.message}`));
      console.log(`[api] starting the learning API on port ${API_PORT}`);
    }
    const running = child;
    for (let i = 0; i < 150; i++) {
      if (await listening()) return true;
      if (running.exitCode !== null || running.killed) return false;
      await sleep(150);
    }
    return false;
  };
  const ready = () => pending ??= start().finally(() => { pending = null; });
  return {
    name: 'lab-api',
    apply: 'serve',
    configureServer(server) {
      if (process.env.LAB_API === 'external') return;
      void ready();  // Warm: the API boots while the page loads.
      // Runs before Vite's own proxy: every /api request waits until the API answers.
      server.middlewares.use('/api', (_req, res, next) => {
        void ready().then(up => {
          if (up) return next();
          res.statusCode = 502;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ ok: false, error: 'The learning API could not start. Its last output is in the details; fix that, then try again.', details: output.slice(-10).join('\n') }));
        });
      });
      const stop = () => { if (child && child.exitCode === null) child.kill(); };
      server.httpServer?.once('close', stop);
      process.once('exit', stop);
    },
  };
}

// If the API stops mid-request, the proxy answers in the API's own error shape instead of an empty 500.
const api = {
  target: `http://127.0.0.1:${API_PORT}`,
  configure: (proxy: { on: (event: 'error', handler: (error: NodeJS.ErrnoException, req: unknown, res: { headersSent?: boolean; writeHead?: (status: number, headers: Record<string, string>) => void; end?: (body: string) => void }) => void) => void }) => {
    proxy.on('error', (error, _req, res) => {
      if (!res?.writeHead || res.headersSent) return;
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end?.(JSON.stringify({ ok: false, error: 'The learning API stopped while answering. Try again: the lab starts it again on the next request.', details: error.code || error.message }));
    });
  },
};

export default defineConfig({ plugins: [react(), labApi()], server: { port: 5173, strictPort: true, proxy: { '/api': api } }, build: { chunkSizeWarningLimit: 1500 } });
