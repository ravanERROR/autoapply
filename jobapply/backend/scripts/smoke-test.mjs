import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { once } from 'node:events';

const temporaryDirectory = await fs.mkdtemp(path.join(os.tmpdir(), 'jobapply-backend-smoke-'));
const csvPath = path.join(temporaryDirectory, 'applications.csv');

process.env.NODE_ENV = 'test';
process.env.APPLICATIONS_CSV = csvPath;

const { createApp } = await import('../dist/app.js');
const server = createApp().listen(0, '127.0.0.1');
await once(server, 'listening');

const address = server.address();
assert(address && typeof address === 'object', 'Smoke server did not expose a TCP address');
const baseUrl = `http://127.0.0.1:${address.port}`;

async function jsonRequest(urlPath, init) {
  const response = await fetch(`${baseUrl}${urlPath}`, init);
  const body = await response.json();
  return { response, body };
}

try {
  const health = await jsonRequest('/health');
  assert.equal(health.response.status, 200);
  assert.equal(health.body.status, 'ok');

  const initialApplications = await jsonRequest('/api/applications');
  assert.equal(initialApplications.response.status, 200);
  assert.deepEqual(initialApplications.body, []);

  const application = {
    platform: 'linkedin',
    jobTitle: 'Engineer, Integrations',
    company: 'Example, Inc.',
    location: 'Pune, India',
    jobUrl: 'https://example.test/jobs/1',
    status: 'applied',
    notes: 'Quoted value: "ready, set, apply"',
  };
  const logged = await jsonRequest('/api/applications/log', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(application),
  });
  assert.equal(logged.response.status, 200);
  assert.equal(logged.body.success, true);

  const applications = await jsonRequest('/api/applications');
  assert.equal(applications.response.status, 200);
  assert.equal(applications.body.length, 1);
  assert.equal(applications.body[0].jobTitle, application.jobTitle);
  assert.equal(applications.body[0].company, application.company);
  assert.equal(applications.body[0].notes, application.notes);

  const defaultFilter = await jsonRequest('/api/filters/default');
  assert.equal(defaultFilter.response.status, 200);
  assert(Array.isArray(defaultFilter.body.keywords));

  const invalidBot = await jsonRequest('/api/bot/start', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      platform: 'unsupported',
      filters: [],
      headless: true,
      slowMo: 0,
      maxApplications: 1,
      exportCsv: false,
    }),
  });
  assert.equal(invalidBot.response.status, 400);

  const cleared = await jsonRequest('/api/applications/clear', { method: 'DELETE' });
  assert.equal(cleared.response.status, 200);
  assert.equal(cleared.body.success, true);

  const afterClear = await jsonRequest('/api/applications');
  assert.deepEqual(afterClear.body, []);
  const csvContents = await fs.readFile(csvPath, 'utf8');
  assert.equal(
    csvContents,
    'id,timestamp,platform,jobTitle,company,location,jobUrl,status,appliedAt,notes\n',
  );

  console.log('Backend smoke test passed (health, CSV log/read/clear, filters, bot validation).');
} finally {
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  await fs.rm(temporaryDirectory, { recursive: true, force: true });
}
