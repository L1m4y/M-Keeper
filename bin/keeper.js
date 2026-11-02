'use strict';
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');

const VERSION = "2.0.0";
const DB_FILE = process.env.MEGA_KEEPER_DB || "accounts.json";

const c = (code) => (process.stdout.isTTY ? `\x1b[${code}m` : '');
const cyan = (s) => `${c('96')}${s}${c('0')}`;
const green = (s) => `${c('92')}${s}${c('0')}`;
const red = (s) => `${c('91')}${s}${c('0')}`;
const yellow = (s) => `${c('93')}${s}${c('0')}`;
const bold = (s) => `${c('1')}${s}${c('0')}`;

function hasBin(name) { try { return spawnSync('command', ['-v', name]).status === 0; } catch { return false; } }

function loadAccounts(dbPath) {
  if (!fs.existsSync(dbPath)) return [];
  try { return JSON.parse(fs.readFileSync(dbPath, 'utf8')); }
  catch { return []; }
}

function saveAccounts(dbPath, data) {
  const tmp = dbPath + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, dbPath);
  try { fs.chmodSync(dbPath, 0o600); } catch {}
}

function writeMegaConfig(email, password) {
  const tmp = path.join(os.tmpdir(), `mega-keeper-${Date.now()}.ini`);
  const escaped = password.replace(/\\/g, '\\\\');
  fs.writeFileSync(tmp, `[Login]\nUsername = ${email}\nPassword = ${escaped}\n`, { mode: 0o600 });
  return tmp;
}

function checkNode(email, password, timeout) {
  const cfg = writeMegaConfig(email, password);
  try {
    const res = spawnSync('megatools', ['df', '--reload', '--human', '--ignore-config-file', '--config', cfg, '--no-ask-password'], {
      timeout: timeout * 1000,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { rc: res.status ?? 1, stdout: (res.stdout || '').trim(), stderr: (res.stderr || '').trim() };
  } catch (err) {
    return { rc: 127, stdout: '', stderr: String(err) };
  } finally {
    try { fs.unlinkSync(cfg); } catch {}
  }
}

function printStatus() {
  const accounts = loadAccounts(DB_FILE);
  console.log(`M-Keeper ${VERSION} :: registered nodes (node)`);
  for (const acc of accounts) {
    console.log(`${(acc.email || '').padEnd(40)} | ${acc.status || 'Pending'}`);
  }
  if (accounts.length === 0) console.log('  [!] NO NODES REGISTERED.');
  console.log(`[i] total nodes: ${accounts.length}`);
}

function prompt(q) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(q, (ans) => { rl.close(); resolve(ans); }));
}

async function addAccount() {
  const email = await prompt('  [?] Mega email: ');
  const password = await prompt('  [?] Password (hidden): ');
  if (!email || !password || !email.includes('@')) {
    console.log('  [!] INVALID NODE. NOTHING SAVED.');
    return;
  }
  const accounts = loadAccounts(DB_FILE);
  if (accounts.some((a) => a.email === email)) {
    console.log('  [!] NODE ALREADY REGISTERED.');
    return;
  }
  accounts.push({ email, password, status: 'Pending' });
  saveAccounts(DB_FILE, accounts);
  console.log('  [+] NODE SECURELY REGISTERED.');
}

async function keepAlive(args) {
  const accounts = loadAccounts(DB_FILE);
  if (!accounts.length) { console.log('  [!] NO TARGETS FOUND. ABORTING.'); return 1; }
  const total = accounts.length;
  const delay = Math.max(0, (args.delay || 5) * 60);
  const timeout = args.timeout || 60;
  const retries = args.retries || 1;
  let success = 0, failed = 0;

  const sig = () => { process.exitCode = 1; };
  process.on('SIGINT', sig);
  process.on('SIGTERM', sig);

  console.log(`M-Keeper ${VERSION} :: maintenance sequence (node)`);
  console.log(`nodes=${total} delay=${args.delay || 5}m timeout=${timeout}s`);

  for (let i = 0; i < total; i++) {
    const acc = accounts[i];
    console.log('\n' + '='.repeat(50));
    console.log(`[>] NODE [${i + 1}/${total}]: ${acc.email}`);
    console.log('  [*] authenticating and checking quota...');
    let rc = 1, out = '', err = '';
    for (let attempt = 0; attempt < retries; attempt++) {
      const r = checkNode(acc.email, acc.password, timeout);
      rc = r.rc; out = r.stdout; err = r.stderr;
      if (rc === 0) break;
      if (attempt < retries - 1) setTimeout(() => {}, 2000);
    }
    if (rc === 0) {
      acc.status = 'Active'; success++;
      console.log('  [+] ACCESS GRANTED');
      for (const line of out.split('\n')) console.log('      ' + line.trim());
    } else {
      acc.status = 'Error'; failed++;
      console.log('  [-] ACCESS DENIED / NETWORK FAILURE');
      if (err) console.log('      ' + err.split('\n')[0]);
    }
    saveAccounts(DB_FILE, accounts);
    // clear megatools cache
    const cache = path.join(os.homedir(), '.cache', 'megatools');
    try { fs.rmSync(cache, { recursive: true, force: true }); } catch {}
    if (i < total - 1 && delay > 0) {
      console.log(`[*] COOLDOWN: ${delay}s`);
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, delay * 1000);
    }
  }

  console.log('\n' + '='.repeat(50));
  console.log('    MAINTENANCE SEQUENCE COMPLETED');
  console.log('=' .repeat(50));
  console.log(`  total nodes checked : ${total}`);
  console.log(`  [+] successful nodes: ${success}`);
  console.log(`  [-] failed nodes     : ${failed}`);
  console.log('=' .repeat(50));
  return failed === 0 ? 0 : 1;
}

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0] || 'status';
  if (cmd === '--version' || cmd === '-V') { console.log('keeper.js ' + VERSION); return; }
  if (cmd === '--help' || cmd === '-h') {
    console.log(`Usage: node keeper.js [status|add|doctor|start]

Environment:
  MEGA_KEEPER_DB   custom account database path
  MEGA_KEEPER_DELAY_MINUTES
  MEGA_KEEPER_TIMEOUT_SECONDS`);
    return;
  }
  if (cmd === 'status') { printStatus(); return; }
  if (cmd === 'doctor') {
    console.log('M-Keeper doctor (node)');
    console.log('node       : ' + process.version);
    const mt = spawnSync('command', ['-v', 'megatools'], { shell: true });
    console.log('megatools  : ' + (mt.status === 0 ? 'present' : 'NOT FOUND'));
    console.log('database   : ' + DB_FILE);
    return;
  }
  if (cmd === 'add') { await addAccount(); return; }
  if (cmd === 'start') {
    const args = { delay: parseInt(process.env.MEGA_KEEPER_DELAY_MINUTES || '5', 10), timeout: parseInt(process.env.MEGA_KEEPER_TIMEOUT_SECONDS || '60', 10), retries: 1 };
    process.exit(await keepAlive(args));
  }
  console.error('unknown command: ' + cmd);
  process.exit(2);
}

main().catch((err) => { console.error(err); process.exit(1); });