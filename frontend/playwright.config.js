import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

// E2E runs its own backend (port 8001, separate e2e.db, offline AI) and frontend (port 5174),
// so it never touches the demo database. Uses the installed Microsoft Edge (no browser download).
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PY = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const backendEnv = {
  DATABASE_URL: "sqlite:///data/e2e.db",
  AI_MODE: "offline",
  MOCK_AI: "false",
  RATE_LIMIT_ENABLED: "false",
  CORS_ORIGINS: "http://127.0.0.1:5174",
  JWT_SECRET: "e2e-secret-0123456789-abcdefghijklmnopqrstuvwxyz",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    // Explicit IPv4: on Windows "localhost" resolves to ::1 first, while uvicorn binds 127.0.0.1.
    baseURL: "http://127.0.0.1:5174",
    channel: process.env.PW_CHANNEL ?? "msedge",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${PY} -m backend.app.seed --reset && ${PY} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001`,
      cwd: ROOT,
      env: backendEnv,
      url: "http://127.0.0.1:8001/ready", // waits until retrieval models are loaded
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5174 --strictPort",
      env: { VITE_API_URL: "http://127.0.0.1:8001" },
      url: "http://127.0.0.1:5174",
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
