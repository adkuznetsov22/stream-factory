import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../live_clipper/static/dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://localhost:8080", "/media": "http://localhost:8080" } },
});
