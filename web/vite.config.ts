import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// API is served by FastAPI on :8000; in dev, Vite proxies /api there.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'MadrasFlow — South Chennai crowd forecast',
        short_name: 'MadrasFlow',
        description: 'Crowd levels for buses, MRTS and metro in South Chennai (simulated demo data).',
        theme_color: '#0f766e',
        background_color: '#f8fafc',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        globIgnores: ['**/MapView-*', '**/RouteMap-*', '**/Depot-*'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => /\/api\/v1\/(routes|stops)/.test(url.pathname),
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'static-api', expiration: { maxAgeSeconds: 24 * 3600, maxEntries: 200 } },
          },
          {
            urlPattern: ({ url }) => /\/api\/v1\/(occupancy|forecast|wait-or-go|vehicle|history)/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'live-api', networkTimeoutSeconds: 3, expiration: { maxEntries: 300, maxAgeSeconds: 24 * 3600 },
              // Mark cache fallbacks so the app can show "Offline · last updated hh:mm"
              plugins: [{
                cachedResponseWillBeUsed: async ({ cachedResponse }: { cachedResponse?: Response }) => {
                  if (!cachedResponse) return cachedResponse
                  const h = new Headers(cachedResponse.headers)
                  h.set('x-from-cache', '1')
                  return new Response(await cachedResponse.blob(), { status: cachedResponse.status, statusText: cachedResponse.statusText, headers: h })
                },
              }],
            },
          },
        ],
      },
    }),
  ],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/docs': 'http://127.0.0.1:8000' } },
  // MapLibre is a large lazy chunk loaded only on "Show map"; the commuter entry stays ~55 KB gzipped.
  build: { target: 'es2020', sourcemap: false, chunkSizeWarningLimit: 900 },
})
