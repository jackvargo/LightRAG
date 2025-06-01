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
      // For production Docker build, output to dist
      // For development build, output to the API webui directory
      outDir: isDev ? 
        path.resolve(__dirname, '../lightrag/api/webui') : 
        path.resolve(__dirname, './dist'),
      emptyOutDir: true,
      sourcemap: !isDev, // Enable sourcemaps in production for debugging
      assetsDir: 'assets',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'axios'],
            ui: ['@radix-ui/react-alert-dialog', '@radix-ui/react-dialog']
          }
        }
      }
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
