'use strict';
const { spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');

const VERSION = "2.0.0";
const DB_FILE = process.env.M_KEEPER_DB || "accounts.json";

const c = (code) => (process.stdout.isTTY ? `\x1b[${code}m` : '');
const cyan = (s) => `${c('96')}${s}${c('0')}`;
const green = (s) => `${c('92')}${s}${c('0')}`;
const red = (s) => `${c('91')}${s}${c('0')}`;
const yellow = (s) => `${c('93')}${s}${c('0')}`;
const bold = (s) => `${c('1')}${s}${c('0')}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const validEmail = (value) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value);
const validCredential = (value) => Boolean(value) && !/[\r\n]/.test(value);

function findBinary(name) {
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, name);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {}
  }
  return null;
}

function loadAccounts(dbPath) {
  if (!fs.existsSync(dbPath)) return [];
  try {
    const data = JSON.parse(fs.readFileSync(dbPath, 'utf8'));
    return Array.isArray(data) ? data.filter((item) => item && typeof item === 'object' && !Array.isArray(item)) : [];
  } catch {
    return [];
  }
}

function saveAccounts(dbPath, data) {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const tmp = `${dbPath}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), { mode: 0o600 });
  try { fs.chmodSync(tmp, 0o600); } catch {}
  fs.renameSync(tmp, dbPath);
  try { fs.chmodSync(dbPath, 0o600); } catch {}
}

function writeMegaConfig(email, password) {
  if (!validCredential(email) || !validCredential(password)) {
    throw new Error('credentials must not contain newlines');
  }
  const suffix = `${process.pid}-${crypto.randomBytes(8).toString('hex')}`;
  const tmp = path.join(os.tmpdir(), `m-keeper-${suffix}.ini`);
  const escaped = password.replace(/\\/g, '\\\\');
  fs.writeFileSync(tmp, `[Login]\nUsername = ${email}\nPassword = ${escaped}\n`, { mode: 0o600, flag: 'wx' });
  return tmp;
}

function checkNode(email, password, timeout) {
  let cfg;
  try {
    cfg = writeMegaConfig(email, password);
  } catch (err) {
    return { rc: 1, stdout: '', stderr: String(err.message || err) };
  }
  try {
    const res = spawnSync('megatools', ['df', '--reload', '--human', '--ignore-config-file', '--config', cfg, '--no-ask-password'], {
      timeout: timeout * 1000,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    if (res.error) {
      const rc = res.error.code === 'ENOENT' ? 127 : res.error.code === 'ETIMEDOUT' ? 124 : 1;
      return { rc, stdout: '', stderr: String(res.error.message || res.error) };
    }
    return { rc: res.status ?? 1, stdout: (res.stdout || '').trim(), stderr: (res.stderr || '').trim() };
  } catch (err) {
    return { rc: 127, stdout: '', stderr: String(err) };
  } finally {
    try { fs.unlinkSync(cfg); } catch {}
  }
}

function printStatus() {
  const accounts = loadAccounts(DB_FILE);
  console.log(`${cyan(`M-Keeper ${VERSION}`)} :: registered nodes (node)`);
  for (const acc of accounts) {
    const email = String(acc.email || '');
    const status = String(acc.status || 'Pending');
    const paint = status === 'Active' ? green : status === 'Error' ? red : yellow;
    console.log(`${email.padEnd(40)} | ${paint(status)}`);
  }
  if (accounts.length === 0) console.log(`  ${red('[!] NO NODES REGISTERED.')}`);
  console.log(`[i] total nodes: ${accounts.length}`);
}

function ask(rl, q) {
  return new Promise((resolve) => rl.question(q, resolve));
}

function promptHidden(q) {
  if (!process.stdin.isTTY || typeof process.stdin.setRawMode !== 'function') {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    return new Promise((resolve) => rl.question(q, (ans) => { rl.close(); resolve(ans); }));
  }
  return new Promise((resolve, reject) => {
    const stdin = process.stdin;
    const wasRaw = stdin.isRaw;
    let value = '';
    process.stdout.write(q);
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding('utf8');
    const cleanup = () => {
      stdin.removeListener('data', onData);
      stdin.setRawMode(Boolean(wasRaw));
      stdin.pause();
    };
    const onData = (chunk) => {
      for (const ch of chunk) {
        if (ch === '\n' || ch === '\r') {
          cleanup();
          process.stdout.write('\n');
          resolve(value);
          return;
        }
        if (ch === '\u0003') {
          cleanup();
          process.stdout.write('\n');
          reject(new Error('aborted'));
          return;
        }
        if (ch === '\u007f' || ch === '\b') {
          value = value.slice(0, -1);
          continue;
        }
        value += ch;
      }
    };
    stdin.on('data', onData);
  });
}

async function addAccount() {
  let email;
  let password;
  try {
    if (process.stdin.isTTY) {
      const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
      email = (await ask(rl, '  [?] Mega email: ')).trim();
      rl.close();
      password = (await promptHidden('  [?] Password (hidden): ')).trim();
    } else {
      const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
      const lines = [];
      await new Promise((resolve) => {
        rl.on('line', (line) => {
          lines.push(line);
          if (lines.length >= 2) resolve();
        });
        rl.on('close', resolve);
      });
      rl.close();
      email = (lines[0] || '').trim();
      password = (lines[1] || '').trim();
    }
  } catch {
    console.log('\n  [!] ABORTED.');
    return;
  }
  if (!validEmail(email) || !validCredential(password)) {
    console.log(`  ${red('[!] INVALID NODE. NOTHING SAVED.')}`);
    return;
  }
  const accounts = loadAccounts(DB_FILE);
  if (accounts.some((a) => String(a.email || '').toLowerCase() === email.toLowerCase())) {
    console.log(`  ${yellow('[!] NODE ALREADY REGISTERED.')}`);
    return;
  }
  accounts.push({ email, password, status: 'Pending' });
  saveAccounts(DB_FILE, accounts);
  console.log(`  ${green('[+] NODE SECURELY REGISTERED.')}`);
}

async function keepAlive(args) {
  const accounts = loadAccounts(DB_FILE);
  if (!accounts.length) { console.log(`  ${red('[!] NO TARGETS FOUND. ABORTING.')}`); return 1; }
  const total = accounts.length;
  const delayMinutes = Number.isFinite(args.delay) ? args.delay : 5;
  const delay = Math.max(0, delayMinutes * 60);
  const timeout = Math.max(1, Number.isFinite(args.timeout) ? args.timeout : 60);
  const retries = Math.max(1, Number.isFinite(args.retries) ? args.retries : 1);
  let checked = 0, success = 0, failed = 0;
  let stopRequested = false;

  const onSignal = () => { stopRequested = true; };
  process.on('SIGINT', onSignal);
  process.on('SIGTERM', onSignal);

  console.log(`${cyan(`M-Keeper ${VERSION}`)} :: maintenance sequence (node)`);
  console.log(`nodes=${total} delay=${delayMinutes}m timeout=${timeout}s`);

  for (let i = 0; i < total; i++) {
    if (stopRequested) break;
    const acc = accounts[i];
    console.log('\n' + bold('='.repeat(50)));
    console.log(`${cyan(`[>] NODE [${i + 1}/${total}]:`)} ${acc.email}`);
    console.log('  [*] authenticating and checking quota...');
    let rc = 1, out = '', err = '';
    for (let attempt = 0; attempt < retries; attempt++) {
      const r = checkNode(String(acc.email || ''), String(acc.password || ''), timeout);
      rc = r.rc; out = r.stdout; err = r.stderr;
      if (rc === 0 || stopRequested) break;
      if (attempt < retries - 1) await sleep(2000);
    }
    checked++;
    if (rc === 0) {
      acc.status = 'Active'; success++;
      console.log(`  ${green('[+] ACCESS GRANTED')}`);
      for (const line of out.split('\n')) console.log('      ' + line.trim());
    } else {
      acc.status = 'Error'; failed++;
      console.log(`  ${red('[-] ACCESS DENIED / NETWORK FAILURE')}`);
      if (err) console.log('      ' + err.split('\n')[0]);
    }
    saveAccounts(DB_FILE, accounts);
    // Remove this account's megatools session cache (stored in os.tmpdir()).
    const digest = crypto.createHash('sha1').update(String(acc.email || '').toLowerCase()).digest('hex');
    try { fs.unlinkSync(path.join(os.tmpdir(), `${digest}.megatools.cache`)); } catch {}
    if (i < total - 1 && delay > 0 && !stopRequested) {
      console.log(`[*] COOLDOWN: ${delay}s`);
      await sleep(delay * 1000);
    }
  }

  process.removeListener('SIGINT', onSignal);
  process.removeListener('SIGTERM', onSignal);

  console.log('\n' + bold('='.repeat(50)));
  console.log(stopRequested ? yellow('    MAINTENANCE SEQUENCE INTERRUPTED') : cyan('    MAINTENANCE SEQUENCE COMPLETED'));
  console.log(bold('='.repeat(50)));
  console.log(`  total nodes registered : ${total}`);
  console.log(`  total nodes checked    : ${checked}`);
  console.log(`  ${green('[+] successful nodes   : ' + success)}`);
  console.log(`  ${red('[-] failed nodes       : ' + failed)}`);
  if (checked < total) console.log(`  ${yellow('[!] nodes skipped      : ' + (total - checked))}`);
  console.log(bold('='.repeat(50)));
  return failed === 0 && checked === total && !stopRequested ? 0 : 1;
}

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0] || 'status';
  if (cmd === '--version' || cmd === '-V') { console.log('keeper.js ' + VERSION); return; }
  if (cmd === '--help' || cmd === '-h') {
    console.log(`Usage: node keeper.js [status|add|doctor|start]

Environment:
  M_KEEPER_DB              custom account database path
  M_KEEPER_DELAY_MINUTES   delay between nodes (default: 5)
  M_KEEPER_TIMEOUT_SECONDS timeout per node (default: 60)
  M_KEEPER_RETRIES         attempts per node (default: 1)`);
    return;
  }
  if (cmd === 'status') { printStatus(); return; }
  if (cmd === 'doctor') {
    console.log('M-Keeper doctor (node)');
    console.log('node       : ' + process.version);
    console.log('megatools  : ' + (findBinary('megatools') || 'NOT FOUND'));
    console.log('database   : ' + DB_FILE + (fs.existsSync(DB_FILE) ? ' (exists)' : ' (not created yet)'));
    const accounts = loadAccounts(DB_FILE);
    console.log('nodes      : ' + accounts.length);
    return;
  }
  if (cmd === 'add') { await addAccount(); return; }
  if (cmd === 'start') {
    const envInt = (name, fallback) => {
      const value = parseInt(process.env[name] || '', 10);
      return Number.isFinite(value) ? value : fallback;
    };
    const args = {
      delay: envInt('M_KEEPER_DELAY_MINUTES', 5),
      timeout: envInt('M_KEEPER_TIMEOUT_SECONDS', 60),
      retries: envInt('M_KEEPER_RETRIES', 1),
    };
    process.exitCode = await keepAlive(args);
    return;
  }
  console.error('unknown command: ' + cmd);
  process.exitCode = 2;
}

main().catch((err) => { console.error(err); process.exitCode = 1; });
