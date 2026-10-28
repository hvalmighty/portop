import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.MPOWER_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/ws": { target: api, ws: true },
      "/healthz": api,
    },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
});
