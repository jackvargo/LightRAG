import { defineConfig } from 'vite'
import path from 'path'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// Import the constant directly to avoid circular dependency
const webuiPrefix = '/webui/' // This should match the value in src/lib/constants.ts

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // For development, enable proxy by default
  const isDev = mode === 'development'
  const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:9621'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    base: webuiPrefix,
    build: {
      outDir: path.resolve(__dirname, '../lightrag/api/webui'),
      emptyOutDir: true
    },
    server: {
      proxy: isDev ? {
        // Proxy all API calls to backend in development
        '^/(auth-status|login|health|documents|query|graph|contexts).*': {
          target: backendUrl,
          changeOrigin: true,
          secure: false
        }
      } : undefined
    }
  }
})
