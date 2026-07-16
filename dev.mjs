import { spawn } from "node:child_process";
import net from "node:net";
import process from "node:process";
import { resolvePythonCommand } from "./scripts/python-command.mjs";

const children = [];
let shuttingDown = false;
const host = "127.0.0.1";
const vitePort = 8765;
const apiPort = 8766;
const isWindows = process.platform === "win32";
const npmCommand = isWindows ? "npm.cmd" : "npm";
const pythonCommand = resolvePythonCommand();

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", (error) => resolve({ free: false, code: error.code }));
    server.once("listening", () => {
      server.close(() => resolve({ free: true }));
    });
    server.listen(port, host);
  });
}

async function assertPortsFree() {
  const checks = await Promise.all([
    isPortFree(vitePort).then((result) => ({ port: vitePort, label: "Vite", ...result })),
    isPortFree(apiPort).then((result) => ({ port: apiPort, label: "Python API", ...result }))
  ]);
  const busy = checks.filter((check) => !check.free);
  if (!busy.length) return;

  console.error("\nMeterMesh cannot start because one of its ports is unavailable:");
  for (const item of busy) {
    const reason = item.code === "EADDRINUSE" ? "already in use" : item.code || "unavailable";
    console.error(`- ${item.label}: http://${host}:${item.port} (${reason})`);
  }
  console.error("\nIf the reason is EADDRINUSE, close the previous MeterMesh terminal window and run the launcher again.");
  process.exit(1);
}

function start(name, command, args) {
  const child = spawn(command, args, {
    stdio: "inherit",
    shell: false
  });
  children.push(child);
  child.on("exit", (code, signal) => {
    if (!shuttingDown) {
      console.log(`\n${name} exited (${signal ?? code}). Stopping MeterMesh...`);
      shutdown(code ?? 1);
    }
  });
  return child;
}

function startNpm(name, args) {
  if (isWindows) {
    const comspec = process.env.ComSpec || "cmd.exe";
    return start(name, comspec, ["/d", "/s", "/c", npmCommand, ...args]);
  }
  return start(name, npmCommand, args);
}

function openDefaultBrowser() {
  if (process.platform !== "darwin") return;
  const child = spawn("open", [`http://${host}:${vitePort}/`], {
    stdio: "ignore",
    shell: false
  });
  child.unref();
}

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 350);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("SIGHUP", () => shutdown(0));

await assertPortsFree();
start("Python API", pythonCommand, ["dashboard_api.py", "--host", host, "--port", String(apiPort)]);
startNpm("Vite", ["run", "dev"]);
setTimeout(openDefaultBrowser, 700);
