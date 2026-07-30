import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    // These three are heavy and each serves a single view: React Flow only the
    // reply-agent chain, CodeMirror only the JSON input fields, Recharts only
    // the multi-model comparison. Splitting them keeps first paint small.
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-flow": ["@xyflow/react"],
          "vendor-editor": ["@uiw/react-codemirror", "@codemirror/lang-json", "@codemirror/theme-one-dark"],
          "vendor-charts": ["recharts"],
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    // The FastAPI layer runs on :8000. Proxying keeps the browser on one
    // origin in dev, so CORS never bites during local development.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
