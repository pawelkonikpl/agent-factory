import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BFF_URL = "http://localhost:8000";

// The dev server proxies /bff and /api to the BFF, so the SPA and the BFF share one
// origin: the session cookie is first-party and SameSite=Strict just works.
// In production, a separate static host serves the built SPA (web/dist/), and a reverse
// proxy in front of it routes /bff and /api to the BFF on the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    // IPv4, not Node's default "localhost" (which can bind only ::1): the dev
    // container's port forward connects to 127.0.0.1.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/bff": { target: BFF_URL },
      "/api": { target: BFF_URL },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
