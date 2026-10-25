'use strict';
/**
 * agentdryrun recorder for JavaScript and TypeScript agents. Zero dependencies.
 *
 *   const { Recorder } = require('agentdryrun');
 *   const rec = new Recorder('agent-events.jsonl', { rules: 'rules.json' });
 *   const issueRefund = rec.tool('refunds.issue', async ({ customer, amountEur }) => { ... });
 *
 * Every call appends one line {tool, params, external_id, occurred_at} BEFORE the function runs, then runs it unchanged.
 * The file is the same one the Python Recorder writes, so `python -m agentdryrun shadow --events agent-events.jsonl` judges it.
 *
 * Honestly: it records the ATTEMPT, not whether it succeeded; only short scalar parameters are kept (and, with `rules` or
 * `fields`, only the ones you name); and it never breaks your agent: if the file cannot be written you get one warning and the
 * call goes ahead. It is a measuring tool, not a security control.
 */
const fs = require('fs');
const crypto = require('crypto');

const MAX_TEXT = 500; // longer strings are prose, not fields a rule reads

const isScalar = (v) =>
  typeof v === 'boolean' || (typeof v === 'number' && Number.isFinite(v)) || (typeof v === 'string' && v.length <= MAX_TEXT);

const isPlainObject = (v) => {
  if (v === null || typeof v !== 'object' || Array.isArray(v)) return false;
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
};

/** A flat object of short scalar values; one nested level becomes `a.b`; lists, long text and everything else are dropped. */
function flatten(value) {
  if (!isPlainObject(value)) return {};
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    if (isScalar(v)) out[k] = v;
    else if (isPlainObject(v)) {
      for (const [k2, v2] of Object.entries(v)) if (isScalar(v2)) out[`${k}.${k2}`] = v2;
    }
  }
  return out;
}

/** Every field name a rules document looks at (the value of any "field" key, anywhere). */
function fieldsInRules(doc) {
  const found = new Set();
  const walk = (o) => {
    if (Array.isArray(o)) o.forEach(walk);
    else if (o && typeof o === 'object') {
      for (const [k, v] of Object.entries(o)) {
        if (k === 'field' && typeof v === 'string') found.add(v);
        else walk(v);
      }
    }
  };
  walk(doc);
  return found;
}

/** One object argument is the parameters; otherwise positional arguments become arg0, arg1... */
function defaultParams(args) {
  if (args.length === 1 && isPlainObject(args[0])) return args[0];
  const o = {};
  args.forEach((a, i) => { o[`arg${i}`] = a; });
  return o;
}

class Recorder {
  /**
   * @param {string} [path] where the events go (JSON Lines, appended)
   * @param {{rules?: string|object, fields?: string[], clock?: () => number}} [options]
   *   rules: a rules file (path or object): keep only the parameters those rules look at
   *   fields: extra parameter names to keep (added to the rules' fields)
   *   clock: returns seconds since 1970; for tests and demos
   */
  constructor(path = 'agent-events.jsonl', options = {}) {
    this.path = path;
    this.clock = options.clock || (() => Date.now() / 1000);
    this.warned = false;
    let keep = options.fields ? new Set(options.fields) : null;
    if (options.rules) {
      const doc = typeof options.rules === 'string'
        ? JSON.parse(fs.readFileSync(options.rules, 'utf8').replace(/^﻿/, ''))
        : options.rules;
      keep = keep || new Set();
      for (const f of fieldsInRules(doc)) keep.add(f);
    }
    this.keep = keep;
  }

  /** Append one event by hand (for code you cannot wrap). Returns the event. */
  record(tool, params = {}, extra = {}) {
    let clean = flatten(params);
    if (this.keep) clean = Object.fromEntries(Object.entries(clean).filter(([k]) => this.keep.has(k)));
    const event = {
      tool: String(tool),
      params: clean,
      external_id: extra.externalId || crypto.randomBytes(6).toString('hex'),
      occurred_at: extra.occurredAt !== undefined ? extra.occurredAt : this.clock(),
    };
    try {
      fs.appendFileSync(this.path, JSON.stringify(event) + '\n');
    } catch (e) {
      if (!this.warned) {
        this.warned = true;
        process.emitWarning(`agentdryrun Recorder could not write ${this.path} (${e.message}); the agent keeps running without recording`);
      }
    }
    return event;
  }

  /**
   * Wrap a function: `const send = rec.tool('payments.send', async ({ amountEur }) => ...)`. Works for sync and async functions.
   * `options.params(...args)` maps the arguments to the parameters you want recorded.
   */
  tool(name, fn, options = {}) {
    const rec = this;
    const mapper = options.params;
    const wrapped = function (...args) {
      let params;
      try {
        params = mapper ? mapper(...args) : defaultParams(args);
      } catch (_) {
        params = {};
      }
      rec.record(name, params);
      return fn.apply(this, args);
    };
    Object.defineProperty(wrapped, 'name', { value: fn.name || name });
    return wrapped;
  }
}

module.exports = { Recorder, flatten, fieldsInRules };
