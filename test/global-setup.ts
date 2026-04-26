import { existsSync, unlinkSync } from 'fs';
import path from 'path';

async function globalSetup() {
  const baseURL = 'http://localhost:8000';
  let serverUp = false;
  try {
    const res = await fetch(`${baseURL}/api/health`);
    serverUp = res.ok;
  } catch {
    serverUp = false;
  }

  if (serverUp) {
    console.log('Reset: server already running, skipping DB delete (handled by test runner before server start)');
    return;
  }

  const dbPath = path.resolve(__dirname, '../db/finally.db');
  if (existsSync(dbPath)) {
    unlinkSync(dbPath);
    console.log('Reset: deleted', dbPath);
  }
}

export default globalSetup;
