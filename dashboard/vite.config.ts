import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the Python governance console JSON API.
// Set VITE_API to point at it (default the local console on :8900).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
