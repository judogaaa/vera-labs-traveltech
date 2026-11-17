import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Dev = :5173 (npm run dev). Preview = :4173 (npm run preview). API = :8000.
  // Note: server.hmr.host alone does NOT open a separate WS port (Vite 8: use server.ws.port).
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Windows: recursive watch on this repo opened ~28k handles and stalled HTTP
    // after "Local:" (TCP accept OK, no response). Disable FS watch for stable localhost;
    // restart `npm run dev` after source edits.
    watch: null,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
  build: {
    // Catalog JSON lives in public/; maplibre stays in the OhRoute lazy chunk.
    chunkSizeWarningLimit: 700,
  },
  optimizeDeps: {
    // Cold-start evidence (Vite 8.3.2): default crawl also scanned
    // artifacts/e2e/*.html + o-hochu-app (~37s "[optimizer] scanning").
    // Pin the app entry; do not hold first HTTP until crawl ends.
    // noDiscovery: skip crawl entirely — only prebundle `include` (avoids
    // post-ready hang while scanning/bundling on Windows + Node 26).
    entries: ['index.html'],
    holdUntilCrawlEnd: false,
    noDiscovery: true,
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-dev-runtime',
      'react/jsx-runtime',
      'react-router-dom',
      'framer-motion',
      'lucide-react',
      // Must be prebundled: raw dist has no ESM default export and blank /oh-route.
      'maplibre-gl',
    ],
  },
})
