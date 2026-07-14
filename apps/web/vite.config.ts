import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Bind IPv4 so 127.0.0.1:5173 works (Windows localhost often resolves to ::1 only).
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:7700",
      "/events": "http://127.0.0.1:7700",
      "/health": "http://127.0.0.1:7700",
    },
  },
  test: {
    environment: "node",
  },
});
