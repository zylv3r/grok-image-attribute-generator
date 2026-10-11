import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
const backend = "http://127.0.0.1:8123";
const proxy: ProxyOptions = {
  target: backend,
  changeOrigin: true,
  configure(server) {
    server.on("proxyReq", (upstream, request) => {
      // Preserve the backend's same-origin checks through the local dev proxy.
      const origin = request.headers.origin;
      if (!origin) return;
      try {
        if (new URL(origin).host === request.headers.host) {
          upstream.setHeader("Origin", backend);
        }
      } catch {
        // Invalid or unrelated origins pass through for the backend to reject.
      }
    });
  },
};
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": proxy,
      "/generated": proxy,
      "/thumbnails": proxy,
    },
  },
});
