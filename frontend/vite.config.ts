import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/",
  server: {
    host: true,
    // Proxy API calls to the backend during `npm run dev` so the browser
    // sees everything as one origin (localhost:5173). This matters beyond
    // convenience: the auth cookies are httpOnly + SameSite=Lax, and a
    // genuinely cross-origin dev setup (5173 -> 8484 directly) wouldn't
    // reliably carry them on <img> requests to /api/media/images/...
    proxy: {
      "/api": {
        target: "http://localhost:8484",
        changeOrigin: true,
      },
    },
  },
})