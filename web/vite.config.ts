import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: {
      "/runs": { target: "http://0.0.0.0:8765", changeOrigin: true },
      "/health": { target: "http://0.0.0.0:8765", changeOrigin: true },
      "/conversations": { target: "http://0.0.0.0:8765", changeOrigin: true },
      "/files": { target: "http://0.0.0.0:8765", changeOrigin: true },
    },
  },
});
