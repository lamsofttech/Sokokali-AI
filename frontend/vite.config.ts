/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  // The dev server forwards API calls to the FastAPI backend, so the browser only talks to one origin.
  const backend = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
  const proxy = { target: backend, changeOrigin: true };

  return {
    plugins: [react(), tailwindcss()],
    // three.js (~900 kB) lives in its own lazily loaded chunk with the avatar; the main bundle stays small.
    build: { chunkSizeWarningLimit: 1000 },
    server: {
      port: 5173,
      proxy: { "/api": proxy, "/health": proxy, "/ready": proxy, "/ws": { ...proxy, ws: true } },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
