import process from 'node:process';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Open the dev server as http://pm.maec.local:5173, never localhost: MAEC One's cookie is
    // set for .maec.local, and a browser sends it only to hosts under that domain.
    allowedHosts: ['.maec.local'],
    // Same origin, as in the container: /api goes to the backend, which asks MAEC One about
    // the cookie. The Host header is kept, so the backend tells MAEC One the address the
    // browser used.
    proxy: { '/api': { target: process.env.MAEC_DEV_API || 'http://localhost:8000', changeOrigin: false } },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
  },
});
