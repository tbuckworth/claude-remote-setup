#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const sourceRoot = process.env.FOOD_CLAUDE_SOURCE_DIR
  || path.join(os.homedir(), 'pyg', 'food-claude');
const launcher = path.join(sourceRoot, 'bin', 'launch-mcp.js');

if (!fs.existsSync(launcher)) {
  console.error(`[food-claude] Upstream checkout not found at ${sourceRoot}.`);
  console.error('[food-claude] Run setup-codex.sh or set FOOD_CLAUDE_SOURCE_DIR.');
  process.exit(1);
}

const child = spawn(process.execPath, [launcher], {
  env: process.env,
  stdio: 'inherit',
});

child.on('error', (error) => {
  console.error(`[food-claude] Could not start upstream MCP launcher: ${error.message}`);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
