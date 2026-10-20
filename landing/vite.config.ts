import { readFileSync } from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const version = readFileSync(path.resolve(import.meta.dirname, '../VERSION'), 'utf8').trim()

// Published at alenabraham.me/eyrie/ (the website unpacks the release tarball there).
export default defineConfig({
  base: '/eyrie/',
  plugins: [react(), tailwindcss()],
  define: { __EYRIE_VERSION__: JSON.stringify(version) },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
      // The app's own components (the Logo, Card), shared rather than copied.
      '@eyrie': path.resolve(import.meta.dirname, '../frontend/src'),
    },
    // Files under ../frontend would otherwise resolve these from frontend/node_modules.
    dedupe: ['react', 'react-dom', 'cn'],
  },
  server: { fs: { allow: ['..'] } },
})
