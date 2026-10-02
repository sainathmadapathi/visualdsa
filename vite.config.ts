import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// When the Flask API is not running, the proxy answers in the API's own error shape instead of an empty 500.
const api = {
  target: 'http://127.0.0.1:5000',
  configure: (proxy: { on: (event: 'error', handler: (error: NodeJS.ErrnoException, req: unknown, res: { headersSent?: boolean; writeHead?: (status: number, headers: Record<string, string>) => void; end?: (body: string) => void }) => void) => void }) => {
    proxy.on('error', (error, _req, res) => {
      if (!res?.writeHead || res.headersSent) return;
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end?.(JSON.stringify({ ok: false, error: 'The learning API is not running. Start it with "python app.py", then try again.', details: error.code || error.message }));
    });
  },
};

export default defineConfig({ plugins: [react()], server: { port: 5173, strictPort: true, proxy: { '/api': api } }, build: { chunkSizeWarningLimit: 1500 } });
