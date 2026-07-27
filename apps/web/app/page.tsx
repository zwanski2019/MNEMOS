import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import {
  getAudit,
  getRepeatFindings,
  getSeverityBreakdown,
  getStats,
  getTotalCost,
} from "@/lib/memory";

// Memory changes on every run, so this page is never cached at build time.
export const dynamic = "force-dynamic";

const SEVERITY_STYLE: Record<string, { dot: string; bar: string }> = {
  critical: { dot: "bg-error", bar: "bg-error" },
  high: { dot: "bg-secondary", bar: "bg-secondary" },
  medium: { dot: "bg-primary-container", bar: "bg-primary-container" },
  low: { dot: "bg-tertiary-container", bar: "bg-tertiary-container" },
  info: { dot: "bg-surface-bright", bar: "bg-surface-bright" },
};
const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

const ACTOR_STYLE: Record<string, string> = {
  scanner: "text-primary",
  gateway: "text-secondary",
  analyst: "text-tertiary",
  operator: "text-on-surface-variant",
};

export default async function OverviewPage() {
  const [stats, cost, severities, audit, repeats] = await Promise.all([
    getStats(),
    getTotalCost(),
    getSeverityBreakdown(),
    getAudit(14),
    getRepeatFindings(),
  ]);

  const totalFindings = severities?.reduce((a, s) => a + s.n, 0) ?? 0;

  return (
    <>
      <TopAppBar subtitle="/ Overview" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
            <StatCard
              title="Targets in Scope"
              icon="target"
              iconClass="text-primary-container"
              value={stats ? String(stats.targets) : "—"}
              foot={
                <span>
                  {stats
                    ? `${stats.scope_decisions} scope rules on record`
                    : "memory unreachable"}
                </span>
              }
              accent
            />

            <div className="bg-level-1 border border-level-2 p-panel_padding flex flex-col gap-2 rounded shadow">
              <div className="flex justify-between items-start">
                <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">
                  Findings by Severity
                </h2>
                <Icon name="pie_chart" className="text-secondary text-sm" />
              </div>
              {severities && totalFindings > 0 ? (
                <>
                  <div className="flex gap-1 w-full h-2 mt-2 rounded overflow-hidden">
                    {SEVERITY_ORDER.filter((s) =>
                      severities.some((x) => x.severity === s),
                    ).map((sev) => {
                      const n = severities.find((x) => x.severity === sev)?.n ?? 0;
                      return (
                        <div
                          key={sev}
                          className={SEVERITY_STYLE[sev]?.bar ?? "bg-surface-bright"}
                          style={{ width: `${(n / totalFindings) * 100}%` }}
                          title={`${sev}: ${n}`}
                        />
                      );
                    })}
                  </div>
                  <div className="font-data-mono text-[10px] text-on-surface-variant mt-auto pt-2 grid grid-cols-3 gap-1">
                    {SEVERITY_ORDER.map((sev) => {
                      const n = severities.find((x) => x.severity === sev)?.n;
                      if (!n) return null;
                      return (
                        <span key={sev} className="flex items-center gap-1">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${SEVERITY_STYLE[sev]?.dot}`}
                          />
                          {sev.slice(0, 4)} ({n})
                        </span>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="font-data-mono text-data-mono text-outline mt-2">
                  {severities ? "no findings yet" : "memory unreachable"}
                </div>
              )}
            </div>

            <StatCard
              title="Assets Discovered"
              icon="lan"
              iconClass="text-tertiary-container"
              value={stats ? String(stats.assets) : "—"}
              foot={
                <span>
                  {stats
                    ? `${stats.artifacts} artifacts · ${stats.embeddings} vectors indexed`
                    : "memory unreachable"}
                </span>
              }
            />
            <StatCard
              title="Total Agent Cost"
              icon="payments"
              iconClass="text-outline"
              value={cost === null ? "—" : `$${cost.toFixed(4)}`}
              foot={
                <span>
                  {stats
                    ? `across ${stats.agent_runs} runs · from agent_runs`
                    : "memory unreachable"}
                </span>
              }
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-gutter h-[calc(100vh-220px)] min-h-[500px]">
            {/* The audit stream, for real */}
            <div className="xl:col-span-2 bg-level-1 border border-level-2 rounded shadow flex flex-col overflow-hidden">
              <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
                <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                  <Icon name="terminal" className="text-primary text-sm" />
                  Audit Stream
                </h2>
                <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                  live from audit_log
                </span>
              </div>
              <div className="flex-1 overflow-y-auto font-data-mono text-data-mono bg-level-0 p-2 space-y-tight_stack">
                {!audit ? (
                  <MemoryUnavailable what="the audit trail" />
                ) : audit.length === 0 ? (
                  <NoRowsYet what="audit rows" />
                ) : (
                  audit.map((row) => (
                    <div
                      key={row.id}
                      className="group flex items-start gap-3 py-1 px-2 hover:bg-level-1 border-l-2 border-transparent hover:border-primary-container transition-colors"
                    >
                      <span className="text-outline shrink-0 whitespace-nowrap">
                        {new Date(row.at).toISOString().slice(11, 23)}
                      </span>
                      <span
                        className={`bg-surface-bright ${ACTOR_STYLE[row.actor] ?? "text-on-surface"} px-1 rounded text-xs shrink-0`}
                      >
                        [{row.actor}]
                      </span>
                      <span className="flex-1 break-all text-on-surface-variant">
                        <span className="text-on-surface">{row.action}</span>{" "}
                        {row.resource ?? ""}
                      </span>
                      <span
                        className={`text-xs shrink-0 px-1 rounded ${
                          row.decision === "deny"
                            ? "text-error font-data-mono-bold"
                            : row.decision === "hit"
                              ? "text-secondary"
                              : "text-primary-fixed-dim"
                        }`}
                      >
                        {row.decision}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex flex-col gap-gutter">
              {/* Dedup, as data */}
              <div className="bg-level-1 border border-level-2 rounded shadow p-panel_padding flex flex-col h-1/2">
                <div className="flex justify-between items-center mb-4 border-b border-level-2 pb-2">
                  <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest flex items-center gap-2">
                    <Icon name="history_edu" className="text-sm" />
                    Recognised From Memory
                  </h2>
                </div>
                <div className="flex-1 flex flex-col gap-3 overflow-y-auto">
                  {!repeats ? (
                    <MemoryUnavailable what="repeat findings" />
                  ) : repeats.length === 0 ? (
                    <NoRowsYet
                      what="repeats"
                      hint="Nothing has been seen twice yet. Run the demo a second time."
                    />
                  ) : (
                    repeats.map((f) => (
                      <div
                        key={f.id}
                        className="bg-surface-container-low p-3 border border-level-2 rounded"
                      >
                        <div className="flex justify-between items-start mb-1 gap-2">
                          <span className="font-data-mono-bold text-data-mono-bold text-sm text-primary">
                            {f.title}
                          </span>
                          <span className="text-xs text-outline font-data-mono whitespace-nowrap">
                            seen {f.times_seen}×
                          </span>
                        </div>
                        <div className="text-xs text-on-surface-variant">
                          Re-reported {f.times_seen - 1}{" "}
                          {f.times_seen - 1 === 1 ? "time" : "times"} and deduped
                          before write.
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Where memory actually lives */}
              <div className="bg-level-1 border border-level-2 rounded shadow p-panel_padding flex flex-col h-1/2">
                <div className="flex justify-between items-center mb-2">
                  <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest flex items-center gap-2">
                    <Icon name="public" className="text-sm" />
                    Memory Layer
                  </h2>
                  <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                    CockroachDB
                  </span>
                </div>
                {!stats ? (
                  <MemoryUnavailable what="table counts" />
                ) : (
                  <div className="flex-1 grid grid-cols-2 gap-x-4 gap-y-1 font-data-mono text-data-mono content-start mt-2">
                    {Object.entries(stats).map(([table, n]) => (
                      <div
                        key={table}
                        className="flex justify-between border-b border-level-2 py-1"
                      >
                        <span className="text-on-surface-variant">{table}</span>
                        <span
                          className={
                            table === "embeddings" || table === "findings"
                              ? "text-primary"
                              : "text-on-surface"
                          }
                        >
                          {n}
                        </span>
                      </div>
                    ))}
                    <div className="col-span-2 text-[10px] text-outline pt-2">
                      embeddings and findings carry distributed vector indexes
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function StatCard({
  title,
  icon,
  iconClass,
  value,
  foot,
  accent,
}: {
  title: string;
  icon: string;
  iconClass: string;
  value: string;
  foot: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="bg-level-1 border border-level-2 p-panel_padding flex flex-col gap-2 rounded shadow relative overflow-hidden group hover:border-outline-variant transition-colors">
      {accent ? (
        <div className="absolute top-0 left-0 w-1 h-full bg-primary-container opacity-50 group-hover:opacity-100 transition-opacity" />
      ) : null}
      <div className="flex justify-between items-start">
        <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">
          {title}
        </h2>
        <Icon name={icon} className={`text-sm ${iconClass}`} />
      </div>
      <div className="font-display-id text-display-id text-on-surface">{value}</div>
      <div className="font-data-mono text-data-mono text-on-surface-variant text-xs mt-auto">
        {foot}
      </div>
    </div>
  );
}
