"use client";

import { Icon } from "@/components/Icon";
import { useState } from "react";
import { TopAppBar } from "@/components/TopAppBar";

type Actor = "analyst" | "scanner" | "gateway";
type Row = {
  ts: string;
  actor: Actor;
  action: string;
  actionClass: string;
  table: string;
  rows: number;
  latency: string;
  latencyClass?: string;
  sql: string;
  params: [string, string][];
  ctx: [string, string][];
};

const ACTOR_COLOR: Record<Actor, string> = {
  analyst: "text-tertiary",
  scanner: "text-primary",
  gateway: "text-secondary",
};

const ROWS: Row[] = [
  {
    ts: "2026-07-05T14:32:00.854", actor: "analyst", action: "SELECT (vector recall)", actionClass: "bg-primary/10 text-primary border-primary/20",
    table: "findings", rows: 5, latency: "41ms",
    sql: "SELECT id, title, target_id, state, created_at\nFROM findings\nWHERE tenant_id = $1\nORDER BY embedding <-> $2\nLIMIT 5;",
    params: [["$1", "'sandbox-alpha' (tenant)"], ["$2", "VECTOR(1024) [0.88, 0.12, -0.44, …]"]],
    ctx: [["Statement class", "SELECT (read-only via MCP)"], ["Index", "findings_vec (distributed)"], ["Rows seen", "5"], ["Latency", "41ms"]],
  },
  {
    ts: "2026-07-05T14:32:01.102", actor: "gateway", action: "SCOPE_CHECK", actionClass: "bg-primary/10 text-primary border-primary/20",
    table: "scope_decisions", rows: 1, latency: "1ms",
    sql: "SELECT effect FROM scope_decisions\nWHERE target_id = $1 AND $2 ~ pattern\nORDER BY created_at DESC LIMIT 1;",
    params: [["$1", "TRG-sandbox-alpha"], ["$2", "'api.sandbox-alpha.test/v2/users'"]],
    ctx: [["Verdict", "ALLOW"], ["Matched rule", "^api\\.sandbox-alpha\\.test/v[1-3]/.*$"], ["Fail mode", "closed (deny-by-default)"], ["Latency", "1ms"]],
  },
  {
    ts: "2026-07-05T14:32:02.331", actor: "gateway", action: "SCOPE_CHECK (deny)", actionClass: "bg-error/10 text-error border-error/20",
    table: "scope_decisions", rows: 1, latency: "1ms", latencyClass: "text-error",
    sql: "SELECT effect FROM scope_decisions\nWHERE target_id = $1 AND $2 ~ pattern\nORDER BY created_at DESC LIMIT 1;",
    params: [["$1", "TRG-sandbox-alpha"], ["$2", "'staging.sandbox-alpha.test'"]],
    ctx: [["Verdict", "DENY"], ["Matched rule", "staging.sandbox-alpha.test"], ["Action", "request rejected at boundary"], ["Latency", "1ms"]],
  },
  {
    ts: "2026-07-05T14:32:03.007", actor: "scanner", action: "INSERT", actionClass: "bg-primary/10 text-primary border-primary/20",
    table: "artifacts", rows: 1, latency: "12ms",
    sql: "INSERT INTO artifacts (tenant_id, asset_id, kind, s3_uri, sha256, bytes)\nVALUES ($1, $2, 'js_bundle', $3, $4, $5)\nON CONFLICT (tenant_id, sha256) DO NOTHING;",
    params: [["$3", "s3://mnemos-artifacts/…/main.js"], ["$4", "sha256:9f2a…fb31"], ["$5", "412088"]],
    ctx: [["Statement class", "INSERT (content-addressed)"], ["Dedup", "ON CONFLICT sha256 → no-op if seen"], ["Rows written", "1"], ["Latency", "12ms"]],
  },
  {
    ts: "2026-07-05T14:32:03.540", actor: "analyst", action: "INSERT (finding)", actionClass: "bg-primary/10 text-primary border-primary/20",
    table: "findings", rows: 1, latency: "18ms",
    sql: "INSERT INTO findings (tenant_id, target_id, title, vuln_class, severity, state, embedding)\nVALUES ($1, $2, $3, 'ssrf', 'high', 'confirmed', $4);",
    params: [["$3", "'Blind SSRF via PDF Generator'"], ["$4", "VECTOR(1024) [0.31, …]"]],
    ctx: [["Dedup gate", "top match 0.62 < threshold → novel"], ["State", "confirmed"], ["Rows written", "1"], ["Latency", "18ms"]],
  },
];

export default function AuditPage() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <>
      <TopAppBar subtitle="SYSTEM.AUDIT_LOG" cost="SYS_OK · every DB touch logged" />
      <div className="flex-1 flex flex-col p-panel_padding gap-4 overflow-hidden">
        <div className="flex gap-4 items-center bg-surface-container-low p-3 rounded border border-outline-variant shrink-0">
          <div className="flex items-center gap-2 text-on-surface-variant">
            <Icon name="filter_list" className="text-[20px]" />
            <span className="font-label-caps text-label-caps uppercase tracking-widest">Filters:</span>
          </div>
          <div className="flex gap-4 flex-1">
            <Filter icon="smart_toy" placeholder="Actor (analyst / scanner / gateway)" />
            <Filter icon="tag" placeholder="Table / resource" />
            <div className="flex-1 relative">
              <Icon name="event" className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]" />
              <select className="w-full bg-surface-container-lowest border border-outline-variant rounded pl-10 pr-8 py-1.5 font-data-mono text-data-mono text-on-surface focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none appearance-none">
                <option>All statement classes</option><option>SELECT</option><option>INSERT</option><option>SCOPE_CHECK</option>
              </select>
            </div>
            <button className="bg-primary/10 border border-primary text-primary font-data-mono-bold text-data-mono-bold px-4 py-1.5 rounded hover:bg-primary/20 transition-colors flex items-center gap-2"><Icon name="download" className="text-[16px]" /> EXPORT</button>
          </div>
        </div>

        <div className="flex-1 bg-surface-container-low border border-outline-variant rounded flex flex-col overflow-hidden">
          <div className="overflow-auto flex-1">
            <div className="grid grid-cols-[190px_130px_1fr_150px_70px_80px] gap-4 px-4 py-3 bg-surface-container-high border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant sticky top-0 z-10">
              <div>TIMESTAMP (UTC)</div><div>ACTOR</div><div>ACTION</div><div>TABLE / SCOPE</div><div className="text-right">ROWS</div><div className="text-right">LATENCY</div>
            </div>
            {ROWS.map((r, i) => (
              <div key={i}>
                <div
                  onClick={() => setOpen(open === i ? null : i)}
                  className={"grid grid-cols-[190px_130px_1fr_150px_70px_80px] gap-4 px-4 py-2.5 border-b border-outline-variant/40 items-center font-data-mono text-data-mono cursor-pointer border-l-2 transition-colors " + (open === i ? "bg-surface-container-highest border-l-primary" : "border-l-transparent hover:bg-surface-container-highest/50 hover:border-l-primary/50")}
                >
                  <div className="text-on-surface-variant">{r.ts}</div>
                  <div className={`flex items-center gap-2 ${ACTOR_COLOR[r.actor]}`}><Icon name="smart_toy" className="text-[14px]" />{r.actor}</div>
                  <div><span className={`px-1.5 py-0.5 rounded text-[11px] border ${r.actionClass}`}>{r.action}</span></div>
                  <div className="truncate text-on-surface-variant">{r.table}</div>
                  <div className="text-right text-on-surface">{r.rows}</div>
                  <div className={"text-right " + (r.latencyClass ?? "text-on-surface")}>{r.latency}</div>
                </div>
                {open === i ? (
                  <div className="bg-level-0 border-b border-outline-variant px-6 py-4 grid grid-cols-1 md:grid-cols-2 gap-6 font-data-mono">
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] text-on-surface-variant uppercase tracking-wider font-label-caps">SQL Source</span>
                        <pre className="bg-surface-container-lowest p-3 rounded border border-outline-variant text-primary text-[12px] overflow-x-auto whitespace-pre-wrap">{r.sql}</pre>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] text-on-surface-variant uppercase tracking-wider font-label-caps">Bound Parameters</span>
                        <div className="flex flex-col gap-1 text-[12px]">
                          {r.params.map(([k, v], j) => (
                            <div key={j} className="grid grid-cols-[48px_1fr] gap-3">
                              <span className="text-on-surface-variant">{k}</span>
                              <span className="text-primary truncate" title={v}>{v}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-on-surface-variant uppercase tracking-wider font-label-caps">Execution Context</span>
                      <div className="bg-surface-container-lowest p-3 rounded border border-outline-variant flex flex-col gap-2 text-[12px]">
                        {r.ctx.map(([k, v], j) => (
                          <div key={j} className="flex justify-between gap-4"><span className="text-on-surface-variant shrink-0">{k}</span><span className="text-on-surface text-right">{v}</span></div>
                        ))}
                      </div>
                      <div className="flex justify-end mt-2">
                        <button className="text-[11px] px-3 py-1 border border-primary/30 text-primary rounded hover:bg-primary/10 transition-colors">DOWNLOAD RAW LOG</button>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          <div className="bg-surface-container-high border-t border-outline-variant p-2 flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant">
            <span>SHOWING {ROWS.length} OF 1,204 RECORDS · click a row for the exact statement + bound params</span>
            <div className="flex gap-2">
              <button aria-label="Previous page" className="p-1 opacity-50" disabled><Icon name="chevron_left" className="text-[20px]" /></button>
              <button aria-label="Next page" className="p-1 hover:text-on-surface"><Icon name="chevron_right" className="text-[20px]" /></button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Filter({ icon, placeholder }: { icon: string; placeholder: string }) {
  return (
    <div className="flex-1 relative">
      <Icon name={icon} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]" />
      <input className="w-full bg-surface-container-lowest border border-outline-variant rounded pl-10 pr-3 py-1.5 font-data-mono text-data-mono text-on-surface placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none" placeholder={placeholder} />
    </div>
  );
}
