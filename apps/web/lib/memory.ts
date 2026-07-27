/**
 * Mission Control's read model.
 *
 * Every figure this dashboard shows is read live out of CockroachDB. There are no
 * fixtures: if the memory layer is unreachable the UI says so, because a recon
 * console that invents numbers when its database is down is worse than one that
 * goes blank.
 *
 * The connection uses `mnemos_web_ro`, a role with SELECT and nothing else
 * (packages/memory/migrations/002_roles.sql). A read-only console cannot be turned
 * into a write path by a bug in a page component.
 */
import { Pool } from "pg";

// Serverless functions are recycled constantly; cache the pool on globalThis so we
// do not open a new connection per request during a burst.
declare global {
  // eslint-disable-next-line no-var
  var __mnemosPool: Pool | undefined;
}

const CONNECTION_STRING =
  process.env.WEB_DATABASE_URL || process.env.DATABASE_URL || "";

export const MEMORY_CONFIGURED = CONNECTION_STRING.length > 0;

function pool(): Pool {
  if (!global.__mnemosPool) {
    global.__mnemosPool = new Pool({
      connectionString: CONNECTION_STRING,
      max: 3,
      idleTimeoutMillis: 10_000,
      connectionTimeoutMillis: 8_000,
      ssl: CONNECTION_STRING.includes("sslmode=disable")
        ? undefined
        : { rejectUnauthorized: true },
    });
  }
  return global.__mnemosPool;
}

/**
 * Run a query, returning null rather than throwing.
 *
 * Pages render an explicit "memory layer unreachable" state on null. Swallowing the
 * error here keeps that decision in one place instead of wrapping every call site
 * in try/catch, and the reason is logged for the server-side trace.
 */
async function q<T>(sql: string, params: unknown[] = []): Promise<T[] | null> {
  if (!MEMORY_CONFIGURED) return null;
  try {
    const res = await pool().query(sql, params);
    return res.rows as T[];
  } catch (err) {
    console.error("[mnemos] memory query failed:", (err as Error).message);
    return null;
  }
}

export type Stats = {
  targets: number;
  assets: number;
  artifacts: number;
  embeddings: number;
  findings: number;
  agent_runs: number;
  audit_log: number;
  scope_decisions: number;
};

export async function getStats(): Promise<Stats | null> {
  const rows = await q<Stats>(`
    SELECT
      (SELECT count(*) FROM targets)         AS targets,
      (SELECT count(*) FROM assets)          AS assets,
      (SELECT count(*) FROM artifacts)       AS artifacts,
      (SELECT count(*) FROM embeddings)      AS embeddings,
      (SELECT count(*) FROM findings)        AS findings,
      (SELECT count(*) FROM agent_runs)      AS agent_runs,
      (SELECT count(*) FROM audit_log)       AS audit_log,
      (SELECT count(*) FROM scope_decisions) AS scope_decisions
  `);
  if (!rows?.[0]) return null;
  // node-postgres returns BIGINT as string to avoid precision loss.
  return Object.fromEntries(
    Object.entries(rows[0]).map(([k, v]) => [k, Number(v)]),
  ) as Stats;
}

export type Finding = {
  id: string;
  title: string;
  severity: string;
  summary: string;
  times_seen: number;
  created_at: string;
  root_domain: string | null;
};

export async function getFindings(limit = 50): Promise<Finding[] | null> {
  return q<Finding>(
    `SELECT f.id, f.title, f.severity, f.summary, f.times_seen, f.created_at,
            t.root_domain
       FROM findings f LEFT JOIN targets t ON t.id = f.target_id
      ORDER BY f.created_at DESC LIMIT $1`,
    [limit],
  );
}

export type Run = {
  id: string;
  pass_no: number;
  status: string;
  model: string | null;
  embed_model: string | null;
  recalled_count: number;
  deduped_count: number;
  written_count: number;
  cost_usd: string;
  started_at: string;
  finished_at: string | null;
  root_domain: string | null;
};

export async function getRuns(limit = 25): Promise<Run[] | null> {
  return q<Run>(
    `SELECT r.id, r.pass_no, r.status, r.model, r.embed_model, r.recalled_count,
            r.deduped_count, r.written_count, r.cost_usd, r.started_at,
            r.finished_at, t.root_domain
       FROM agent_runs r LEFT JOIN targets t ON t.id = r.target_id
      ORDER BY r.started_at DESC LIMIT $1`,
    [limit],
  );
}

export type AuditRow = {
  id: string;
  actor: string;
  action: string;
  decision: string;
  resource: string | null;
  detail: Record<string, unknown>;
  at: string;
};

export async function getAudit(limit = 60): Promise<AuditRow[] | null> {
  return q<AuditRow>(
    `SELECT id, actor, action, decision, resource, detail, at
       FROM audit_log ORDER BY at DESC LIMIT $1`,
    [limit],
  );
}

export type ScopeRule = {
  id: string;
  pattern: string;
  effect: string;
  reason: string;
  decided_by: string;
  decided_at: string;
  root_domain: string | null;
};

export async function getScope(): Promise<ScopeRule[] | null> {
  return q<ScopeRule>(
    `SELECT s.id, s.pattern, s.effect, s.reason, s.decided_by, s.decided_at,
            t.root_domain
       FROM scope_decisions s LEFT JOIN targets t ON t.id = s.target_id
      ORDER BY s.decided_at DESC`,
  );
}

export type Target = {
  id: string;
  name: string;
  root_domain: string;
  authorisation: string;
  created_at: string;
  asset_count: number;
  finding_count: number;
};

export async function getTargets(): Promise<Target[] | null> {
  const rows = await q<Target>(
    `SELECT t.id, t.name, t.root_domain, t.authorisation, t.created_at,
            (SELECT count(*) FROM assets   a WHERE a.target_id = t.id) AS asset_count,
            (SELECT count(*) FROM findings f WHERE f.target_id = t.id) AS finding_count
       FROM targets t ORDER BY t.created_at DESC`,
  );
  return rows?.map((r) => ({
    ...r,
    asset_count: Number(r.asset_count),
    finding_count: Number(r.finding_count),
  })) ?? null;
}

export type MemoryChunk = {
  id: string;
  content: string;
  model: string;
  chunk_idx: number;
  created_at: string;
  root_domain: string | null;
};

export async function getEmbeddings(limit = 25): Promise<MemoryChunk[] | null> {
  return q<MemoryChunk>(
    `SELECT e.id, e.content, e.model, e.chunk_idx, e.created_at, t.root_domain
       FROM embeddings e LEFT JOIN targets t ON t.id = e.target_id
      ORDER BY e.created_at DESC LIMIT $1`,
    [limit],
  );
}

export type Artifact = {
  sha256: string;
  s3_bucket: string | null;
  s3_key: string;
  byte_len: number;
  content_type: string | null;
};

export async function getArtifacts(limit = 25): Promise<Artifact[] | null> {
  const rows = await q<Artifact>(
    `SELECT sha256, s3_bucket, s3_key, byte_len, content_type
       FROM artifacts ORDER BY byte_len DESC LIMIT $1`,
    [limit],
  );
  return rows?.map((r) => ({ ...r, byte_len: Number(r.byte_len) })) ?? null;
}

/** Aggregate spend across every run — the number the cost ceiling is enforced from. */
export async function getTotalCost(): Promise<number | null> {
  const rows = await q<{ total: string }>(
    `SELECT coalesce(sum(cost_usd), 0)::STRING AS total FROM agent_runs`,
  );
  return rows?.[0] ? Number(rows[0].total) : null;
}

export type SeverityCount = { severity: string; n: number };

export async function getSeverityBreakdown(): Promise<SeverityCount[] | null> {
  const rows = await q<{ severity: string; n: string }>(
    `SELECT severity, count(*) AS n FROM findings GROUP BY severity`,
  );
  return rows?.map((r) => ({ severity: r.severity, n: Number(r.n) })) ?? null;
}

/** Findings memory has seen more than once — the dedup story, as data. */
export async function getRepeatFindings(): Promise<Finding[] | null> {
  return q<Finding>(
    `SELECT f.id, f.title, f.severity, f.summary, f.times_seen, f.created_at,
            t.root_domain
       FROM findings f LEFT JOIN targets t ON t.id = f.target_id
      WHERE f.times_seen > 1 ORDER BY f.times_seen DESC LIMIT 10`,
  );
}
