// ForkReason V1 — production process definitions.
//
// Three durable processes, matching the architecture:
//   forkreason-web     Next.js frontend (nginx upstream)
//   forkreason-api     FastAPI (loopback only; nginx proxies /api)
//   forkreason-worker  Durable analysis worker (no listener at all)
//
// The worker is separate on purpose: repository analysis must never run inside
// an HTTP request, and a crashed worker must not take the API down with it.
//
// Nothing here holds a key that could sign for a user. Every state-changing
// GenLayer action is signed by the visitor's own browser wallet.

const fs = require("fs");
const path = require("path");

const ROOT = "/root/ForkReason";
const NODE_BIN = "/root/.nvm/versions/node/v22.23.3/bin";
const VENV_PYTHON = `${ROOT}/.venv/bin/python`;

// Read .env at config-parse time so env blocks can reference its values.
function readEnv(file) {
  const out = {};
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[trimmed.slice(0, idx).trim()] = value;
  }
  return out;
}

const env = readEnv(path.join(ROOT, ".env"));

// Resolve a GitHub token from the environment first, then .env, then the `gh`
// CLI's own store. Production was running with an empty GITHUB_TOKEN: .env had
// the key with no value, so the API went out unauthenticated and inherited
// GitHub's 60 requests/hour anonymous limit instead of 5000. Under load that
// surfaced as `github_rate_limited` on ordinary repository validation. Falling
// back to `gh` keeps the deployment authenticated without duplicating a secret
// in a second place, and without ever writing it to a file here.
function resolveGithubToken() {
  const fromProcess = process.env.GITHUB_TOKEN;
  if (fromProcess && fromProcess.trim()) return fromProcess.trim();
  const fromFile = env.GITHUB_TOKEN;
  if (fromFile && fromFile.trim()) return fromFile.trim();
  try {
    const hosts = fs.readFileSync(
      path.join(process.env.HOME || "/root", ".config/gh/hosts.yml"),
      "utf8"
    );
    const match = hosts.match(/oauth_token:\s*(\S+)/);
    if (match) return match[1];
  } catch {
    // gh is not installed or not authenticated; fall through.
  }
  return "";
}

// A process-scoped Studio Mode proxy must never leak into production: PM2's
// daemon inherits whatever shell started it, and a stray HTTPS_PROXY silently
// breaks every outbound call the API makes (GitHub validation failed exactly
// this way before this was pinned).
const SCRUBBED = {};
for (const key of [
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
  "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE",
  "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SURPLUS_API_KEY",
  "FORKREASON_STUB_MODE",
]) {
  SCRUBBED[key] = "";
}

const common = {
  ...SCRUBBED,
  NODE_PATH: NODE_BIN,
  PYTHONPATH: `${ROOT}/apps/api`,
  PYTHONUNBUFFERED: "1",
  APP_ENV: env.APP_ENV || "production",
  APP_URL: env.APP_URL || "https://forkreason.bydx.fun",
  DATABASE_URL: env.DATABASE_URL,
  SNAPSHOT_DIR: env.SNAPSHOT_DIR || "/var/lib/forkreason/snapshots",
  LOG_LEVEL: env.LOG_LEVEL || "INFO",
  ANALYSIS_MAX_REPO_MB: env.ANALYSIS_MAX_REPO_MB || "120",
  ANALYSIS_MAX_FILE_MB: env.ANALYSIS_MAX_FILE_MB || "4",
  ANALYSIS_MAX_FILES: env.ANALYSIS_MAX_FILES || "6000",
  ANALYSIS_MAX_COMMITS: env.ANALYSIS_MAX_COMMITS || "6000",
  ANALYSIS_TIMEOUT_SECONDS: env.ANALYSIS_TIMEOUT_SECONDS || "240",
  ANALYSIS_MAX_EVIDENCE_ITEMS: env.ANALYSIS_MAX_EVIDENCE_ITEMS || "400",
  ANALYSIS_WORKER_CONCURRENCY: env.ANALYSIS_WORKER_CONCURRENCY || "2",
};

const appEnv = {
  ...common,
  API_HOST: "127.0.0.1",
  API_PORT: "8421",
  CORS_ORIGINS: env.CORS_ORIGINS || "https://forkreason.bydx.fun",
  TRUSTED_PROXIES: "127.0.0.1,::1",
  GITHUB_TOKEN: resolveGithubToken(),
  GITHUB_API_BASE_URL: env.GITHUB_API_BASE_URL || "https://api.github.com",
};

module.exports = {
  apps: [
    {
      name: "forkreason-api",
      script: VENV_PYTHON,
      args: "-m uvicorn forkreason.main:app --host 127.0.0.1 --port 8421 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1",
      interpreter: "none",
      cwd: ROOT,
      env: appEnv,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "600M",
      error_file: `${ROOT}/logs/api-error.log`,
      out_file: `${ROOT}/logs/api-out.log`,
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      watch: false,
      max_restarts: 10,
      restart_delay: 4000,
      kill_timeout: 8000,
    },
    {
      name: "forkreason-worker",
      script: VENV_PYTHON,
      args: "-m forkreason.jobs.runner",
      interpreter: "none",
      cwd: ROOT,
      env: appEnv,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "2G",
      error_file: `${ROOT}/logs/worker-error.log`,
      out_file: `${ROOT}/logs/worker-out.log`,
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      watch: false,
      // A worker restart must be quick: a crashed job is recovered by lease
      // expiry, so long retry backoff would stall the queue.
      max_restarts: 15,
      restart_delay: 3000,
      kill_timeout: 15000,
    },
    {
      name: "forkreason-web",
      // Run the standalone server bundle directly, which is what Next requires
      // under `output: "standalone"`. Two earlier shapes were wrong:
      //   `npx next start`  - PM2 supervised the wrapper, so stopping it left
      //     `next-server` alive holding :3112; the next restart died with
      //     EADDRINUSE and the orphan served a stale build, which is why every
      //     case route returned 404 while the API returned 200.
      //   `node next/dist/bin/next start` - refused outright by Next under
      //     standalone output ("does not work with output: standalone").
      // The trace root is the monorepo, so the entrypoint lands under
      // apps/web/ inside the bundle rather than at its root.
      script: `${ROOT}/apps/web/.next/standalone/apps/web/server.js`,
      interpreter: `${NODE_BIN}/node`,
      cwd: `${ROOT}/apps/web`,
      env: {
        ...common,
        PATH: `${NODE_BIN}:/usr/local/bin:/usr/bin:/bin`,
        NODE_ENV: "production",
        PORT: "3112",
        NEXT_PUBLIC_APP_URL: env.NEXT_PUBLIC_APP_URL || "https://forkreason.bydx.fun",
        NEXT_PUBLIC_API_URL: env.NEXT_PUBLIC_API_URL || "",
        NEXT_PUBLIC_GENLAYER_NETWORK: env.NEXT_PUBLIC_GENLAYER_NETWORK || "",
        NEXT_PUBLIC_GENLAYER_RPC_URL: env.NEXT_PUBLIC_GENLAYER_RPC_URL || "",
        NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS:
          env.NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS || "",
        NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID: env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "",
      },
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "900M",
      error_file: `${ROOT}/logs/web-error.log`,
      out_file: `${ROOT}/logs/web-out.log`,
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      watch: false,
      max_restarts: 10,
      restart_delay: 4000,
      kill_timeout: 8000,
    },
  ],
};
