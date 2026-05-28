import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 8765,
    strictPort: true,
    proxy: {
      "/data.json": "http://127.0.0.1:8766",
      "/api/usage": "http://127.0.0.1:8766"
    }
  }
});
