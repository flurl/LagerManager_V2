import { execSync } from 'child_process'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { VitePWA } from 'vite-plugin-pwa'

function getGitInfo() {
  try {
    const count = execSync('git rev-list --count HEAD').toString().trim()
    const hash = execSync('git rev-parse --short HEAD').toString().trim()
    return { count, hash }
  } catch {
    return { count: '0', hash: 'unknown' }
  }
}

const { count: gitCount, hash: gitHash } = getGitInfo()

export default defineConfig({
  define: {
    __APP_COMMIT_COUNT__: JSON.stringify(gitCount),
    __APP_COMMIT_HASH__: JSON.stringify(gitHash),
  },
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['vite.svg', 'pwa-192x192.png', 'pwa-512x512.png'],
      manifest: {
        name: 'LagerManager',
        short_name: 'LagerMgr',
        description: 'Warehouse Management System',
        theme_color: '#1565C0',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/stock-count',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      devOptions: {
        enabled: true,
        type: 'module',
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2,ttf,eot}'],
        navigateFallback: 'index.html',
        // Backend-served paths must never be hijacked by the SPA's SW
        navigateFallbackDenylist: [/^\/admin/, /^\/api/, /^\/static/, /^\/media/],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => /\.(woff2?|ttf|eot)(\?.*)?$/.test(url.pathname),
            handler: 'CacheFirst',
            options: {
              cacheName: 'font-cache',
              expiration: { maxEntries: 20, maxAgeSeconds: 365 * 24 * 60 * 60 },
            },
          },
          {
            urlPattern: ({ url, request }) =>
              request.mode === 'navigate' &&
              !/^\/(admin|api|static|media)(\/|$)/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'navigation-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 10, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/locations/'),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'locations-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/stock-count/articles/'),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'stock-count-articles-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/stock-count/entries/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'stock-count-entries-cache',
              expiration: { maxEntries: 200, maxAgeSeconds: 3600 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
      '/admin': { target: 'http://localhost:8000', changeOrigin: true },
      '/static': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  preview: {
    port: 5171,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
      '/admin': { target: 'http://localhost:8000', changeOrigin: true },
      '/static': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
