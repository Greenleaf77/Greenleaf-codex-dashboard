import { spawn, spawnSync } from "node:child_process";
import process from "node:process";
import { fileURLToPath } from "node:url";

function candidateCommands() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push(process.env.PYTHON);
  candidates.push("python", "python3");
  return [...new Set(candidates)];
}

export function resolvePythonCommand() {
  for (const command of candidateCommands()) {
    const result = spawnSync(command, ["--version"], {
      stdio: "ignore",
      shell: false
    });
    if (!result.error && result.status === 0) {
      return command;
    }
  }
  throw new Error('Python runtime not found. Set the "PYTHON" environment variable or install a "python" or "python3" command.');
}

function run() {
  const args = process.argv.slice(2);
  if (!args.length) {
    console.error("Usage: node scripts/python-command.mjs <script> [args...]");
    process.exit(1);
  }

  const command = resolvePythonCommand();
  const child = spawn(command, args, {
    stdio: "inherit",
    shell: false
  });

  child.on("error", (error) => {
    console.error(`Failed to launch ${command}: ${error.message}`);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    process.exit(code ?? 1);
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  run();
}
