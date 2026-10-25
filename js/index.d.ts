export interface RecorderOptions {
  /** A rules file (path) or a rules object: keep only the parameters those rules look at. */
  rules?: string | object;
  /** Extra parameter names to keep (added to the rules' fields). */
  fields?: string[];
  /** Returns seconds since 1970; for tests and demos. */
  clock?: () => number;
}

export interface RecordExtra {
  externalId?: string;
  occurredAt?: number;
}

export interface RecordedEvent {
  tool: string;
  params: Record<string, string | number | boolean>;
  external_id: string;
  occurred_at: number;
}

export class Recorder {
  constructor(path?: string, options?: RecorderOptions);
  /** Append one event by hand. Returns the event. */
  record(tool: string, params?: unknown, extra?: RecordExtra): RecordedEvent;
  /** Wrap a sync or async function; the attempt is recorded before it runs. */
  tool<F extends (...args: any[]) => any>(name: string, fn: F, options?: { params?: (...args: Parameters<F>) => unknown }): F;
}

export function flatten(value: unknown): Record<string, string | number | boolean>;
export function fieldsInRules(doc: unknown): Set<string>;
