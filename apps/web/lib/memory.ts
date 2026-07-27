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

/* ------------------------------------------------------------------ *
 * Memory intelligence — the reads that make this a memory layer
 * rather than a findings table.
 * ------------------------------------------------------------------ */

/** Half-life must match packages/memory/mnemos_memory/intelligence.py. */
const CONFIDENCE_HALF_LIFE_DAYS = 14;
const MIN_CONFIDENCE = 0.05;

export function confidenceFor(lastConfirmedAt: string | Date): number {
  const then = new Date(lastConfirmedAt).getTime();
  const ageDays = Math.max(0, (Date.now() - then) / 86_400_000);
  const decayed = Math.pow(0.5, ageDays / CONFIDENCE_HALF_LIFE_DAYS);
  return Math.max(MIN_CONFIDENCE, Number(decayed.toFixed(4)));
}

export type ScoredFinding = Finding & {
  status: string;
  regression_count: number;
  last_confirmed_at: string;
  confidence: number;
};

export async function getScoredFindings(limit = 100): Promise<ScoredFinding[] | null> {
  const rows = await q<ScoredFinding>(
    `SELECT f.id, f.title, f.severity, f.summary, f.times_seen, f.created_at,
            f.status, f.regression_count, f.last_confirmed_at, t.root_domain
       FROM findings f LEFT JOIN targets t ON t.id = f.target_id
      ORDER BY f.last_confirmed_at DESC LIMIT $1`,
    [limit],
  );
  return (
    rows?.map((r) => ({
      ...r,
      times_seen: Number(r.times_seen),
      regression_count: Number(r.regression_count),
      confidence: confidenceFor(r.last_confirmed_at),
    })) ?? null
  );
}

export type Correlation = {
  kind: "artifact" | "finding";
  key: string;
  targets: string[];
  occurrences: number;
  detail: string;
};

/**
 * Things memory can see that no single scan can: the same bytes, or the same
 * conclusion, reaching more than one estate.
 */
export async function getCorrelations(): Promise<Correlation[] | null> {
  const artifacts = await q<{
    sha256: string; n_targets: string; occurrences: string; domains: string[]; bytes: string;
  }>(
    `SELECT a.sha256, count(DISTINCT a.target_id) AS n_targets, count(*) AS occurrences,
            array_agg(DISTINCT t.root_domain) AS domains, max(a.byte_len) AS bytes
       FROM artifacts a JOIN targets t ON t.id = a.target_id
      GROUP BY a.sha256 HAVING count(DISTINCT a.target_id) > 1
      ORDER BY n_targets DESC LIMIT 20`,
  );
  const findings = await q<{
    title: string; severity: string; n_targets: string; occurrences: string; domains: string[];
  }>(
    `SELECT f.title, f.severity, count(DISTINCT f.target_id) AS n_targets,
            count(*) AS occurrences, array_agg(DISTINCT t.root_domain) AS domains
       FROM findings f JOIN targets t ON t.id = f.target_id
      GROUP BY f.title, f.severity HAVING count(DISTINCT f.target_id) > 1
      ORDER BY n_targets DESC LIMIT 20`,
  );
  if (artifacts === null && findings === null) return null;

  return [
    ...(artifacts ?? []).map((a) => ({
      kind: "artifact" as const,
      key: a.sha256,
      targets: (a.domains ?? []).filter(Boolean),
      occurrences: Number(a.occurrences),
      detail: `identical ${Number(a.bytes)}-byte artifact on ${a.n_targets} estates`,
    })),
    ...(findings ?? []).map((f) => ({
      kind: "finding" as const,
      key: f.title,
      targets: (f.domains ?? []).filter(Boolean),
      occurrences: Number(f.occurrences),
      detail: `${f.severity} finding reached independently on ${f.n_targets} estates`,
    })),
  ];
}

export type Snapshot = Record<string, number>;

/**
 * Memory as it stood at a past instant, via CockroachDB AS OF SYSTEM TIME.
 *
 * The clause has to be top-level, so the reads run inside a transaction opened at
 * that timestamp — which also guarantees every count comes from the same instant.
 * Returns null when the timestamp is outside the cluster's GC window, which is a
 * real answer rather than an error.
 */
export async function getSnapshotAt(minutesAgo: number): Promise<Snapshot | null> {
  if (!MEMORY_CONFIGURED) return null;
  const tables = [
    "targets", "assets", "artifacts", "embeddings",
    "findings", "agent_runs", "audit_log", "scope_decisions",
  ];
  const client = await pool().connect().catch(() => null);
  if (!client) return null;
  try {
    await client.query(`BEGIN AS OF SYSTEM TIME '-${Math.round(minutesAgo)}m'`);
    const out: Snapshot = {};
    for (const t of tables) {
      const r = await client.query(`SELECT count(*) AS n FROM ${t}`);
      out[t] = Number(r.rows[0].n);
    }
    await client.query("COMMIT");
    return out;
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    console.warn("[mnemos] time travel rejected:", (err as Error).message);
    return null;
  } finally {
    client.release();
  }
}

/** Vector search over the distributed index — the memory layer, visibly at work. */
export type RecallHit = {
  kind: "embedding" | "finding";
  content: string;
  distance: number;
};

export async function recallByText(
  queryText: string,
  k = 8,
): Promise<RecallHit[] | null> {
  if (!queryText.trim()) return [];
  // The web tier has no embedder (and must not have AWS credentials), so it
  // searches on the stored text rather than re-embedding the query. The vector
  // index still ranks: we pull the nearest neighbours of the best textual match.
  const seed = await q<{ embedding: string }>(
    `SELECT embedding::STRING AS embedding FROM embeddings
      WHERE content ILIKE '%' || $1 || '%' LIMIT 1`,
    [queryText.trim()],
  );
  if (seed === null) return null;
  if (seed.length === 0) return [];

  const vec = seed[0].embedding;
  const emb = await q<{ content: string; distance: string }>(
    `SELECT content, embedding <=> $1 AS distance FROM embeddings
      ORDER BY embedding <=> $1 LIMIT $2`,
    [vec, k],
  );
  const fnd = await q<{ content: string; distance: string }>(
    `SELECT title || ' — ' || summary AS content, embedding <=> $1 AS distance
       FROM findings ORDER BY embedding <=> $1 LIMIT $2`,
    [vec, k],
  );

  return [
    ...(emb ?? []).map((r) => ({
      kind: "embedding" as const, content: r.content, distance: Number(r.distance),
    })),
    ...(fnd ?? []).map((r) => ({
      kind: "finding" as const, content: r.content, distance: Number(r.distance),
    })),
  ].sort((a, b) => a.distance - b.distance);
}
