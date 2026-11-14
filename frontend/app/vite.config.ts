import { defineConfig } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import babel from "@rolldown/plugin-babel";

// App calls the API on its own origin;
// the dev servers forward the API paths to wke-api.
const apiOrigin = process.env.WKE_API_ORIGIN ?? "http://localhost:8000";
const target = { target: apiOrigin, changeOrigin: true, ws: false };
const apiProxy = {
  "/api": target,
  "/llms.txt": target,
  "/sitemap.xml": target,
  "/openapi.json": target,
  "/mcp": target,
};

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    babel({ presets: [reactCompilerPreset()] }),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    host: true,
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
