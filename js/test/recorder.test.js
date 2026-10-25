'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { Recorder, flatten, fieldsInRules } = require('..');

const RULES = path.join(__dirname, '..', '..', 'examples', 'rules-front-office.json');
const tmp = () => path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'adr-')), 'events.jsonl');
const read = (p) => fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));

test('records before the function runs and returns its value', () => {
  const file = tmp();
  const rec = new Recorder(file, { fields: ['amountEur'] });
  const seen = [];
  const send = rec.tool('payments.send', ({ amountEur, vendor }) => {
    seen.push(read(file).length); // the line is already there when the body runs
    return `sent ${amountEur}`;
  });
  assert.strictEqual(send({ amountEur: 320, vendor: 'Delta' }), 'sent 320');
  assert.deepStrictEqual(seen, [1]);
  const [ev] = read(file);
  assert.deepStrictEqual(Object.keys(ev), ['tool', 'params', 'external_id', 'occurred_at']); // same shape as the Python Recorder
  assert.strictEqual(ev.tool, 'payments.send');
  assert.deepStrictEqual(ev.params, { amountEur: 320 }); // vendor is not in `fields`
  assert.ok(ev.external_id.length >= 8 && ev.occurred_at > 1e9);
});

test('async functions are recorded and awaited; a thrown error still leaves the attempt recorded', async () => {
  const file = tmp();
  const rec = new Recorder(file);
  const run = rec.tool('jobs.run', async ({ jobId }) => { await null; return jobId * 2; });
  assert.strictEqual(await run({ jobId: 21 }), 42);
  const boom = rec.tool('payments.send', () => { throw new Error('bank down'); });
  assert.throws(() => boom({ amountEur: 5 }), /bank down/);
  assert.deepStrictEqual(read(file).map((e) => e.tool), ['jobs.run', 'payments.send']);
});

test('keeps only short scalars; one nested level is flattened; lists and long text are dropped', () => {
  assert.deepStrictEqual(
    flatten({ a: 1, b: 'x', c: true, d: 'y'.repeat(600), e: [1, 2], f: { g: 3, h: { i: 4 } }, n: NaN }),
    { a: 1, b: 'x', c: true, 'f.g': 3 },
  );
  assert.deepStrictEqual(flatten('not an object'), {});
  assert.deepStrictEqual(flatten(null), {});
});

test('rules decide which fields reach the file', () => {
  const file = tmp();
  const rec = new Recorder(file, { rules: RULES });
  rec.record('invoices.create', { customer: 'Jane Doe', amount_eur: 450, address: 'somewhere' });
  assert.deepStrictEqual(read(file)[0].params, { amount_eur: 450 });
  assert.ok(fieldsInRules({ tools: { x: { deny: [{ when: { field: 'amount_eur' } }] } } }).has('amount_eur'));
});

test('a params mapper and positional arguments', () => {
  const file = tmp();
  const rec = new Recorder(file);
  const a = rec.tool('refunds.issue', (customer, amount) => 'ok', { params: (customer, amount) => ({ customer, amount_eur: amount }) });
  a('C-1', 80);
  const b = rec.tool('math.add', (x, y) => x + y);
  assert.strictEqual(b(1, 2), 3);
  const evs = read(file);
  assert.deepStrictEqual(evs[0].params, { customer: 'C-1', amount_eur: 80 });
  assert.deepStrictEqual(evs[1].params, { arg0: 1, arg1: 2 });
});

test('never breaks the agent when the file cannot be written: one warning, then the call goes ahead', () => {
  const bad = path.join(os.tmpdir(), 'no-such-dir-adr', 'x', 'events.jsonl');
  const warnings = [];
  const onWarning = (w) => warnings.push(w.message);
  process.on('warning', onWarning);
  const rec = new Recorder(bad);
  const f = rec.tool('payments.send', () => 'sent');
  assert.strictEqual(f({ a: 1 }), 'sent');
  assert.strictEqual(f({ a: 2 }), 'sent');
  return new Promise((resolve) => setImmediate(() => {
    process.removeListener('warning', onWarning);
    assert.strictEqual(warnings.filter((m) => m.includes('could not write')).length, 1);
    resolve();
  }));
});

test('the wrapper keeps the function name', () => {
  const rec = new Recorder(tmp());
  function sendPayment() {}
  assert.strictEqual(rec.tool('payments.send', sendPayment).name, 'sendPayment');
});
