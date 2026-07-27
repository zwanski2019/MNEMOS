import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import {
  getCorrelations,
  getScoredFindings,
  getSnapshotAt,
  getStats,
} from "@/lib/memory";

export const dynamic = "force-dynamic";

const OFFSETS = [1, 10, 45, 120];

export default async function IntelligencePage() {
  const [correlations, scored, now, ...snapshots] = await Promise.all([
    getCorrelations(),
    getScoredFindings(40),
    getStats(),
    ...OFFSETS.map((m) => getSnapshotAt(m)),
  ]);

  const regressed = scored?.filter((f) => f.status === "regressed") ?? [];
  const stale = scored?.filter((f) => f.confidence < 0.5) ?? [];

  return (
    <>
      <TopAppBar subtitle="/ Intelligence" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          {/* Time travel */}
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="history" className="text-primary text-sm" />
                Time Travel
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                AS OF SYSTEM TIME
              </span>
            </div>
            <div className="p-panel_padding">
              <p className="font-data-mono text-data-mono text-on-surface-variant mb-4">
                What memory held at a past instant — reconstructed from the committed
                row state, not replayed from a log. This is the question that matters
                after an incident:{" "}
                <span className="text-primary">
                  what did the agent know, and what was it authorised to do?
                </span>
              </p>
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-3 py-2 font-label-caps">When</th>
                      <th className="px-3 py-2 font-label-caps text-right">Findings</th>
                      <th className="px-3 py-2 font-label-caps text-right">Embeddings</th>
                      <th className="px-3 py-2 font-label-caps text-right">Scope rules</th>
                      <th className="px-3 py-2 font-label-caps text-right">Audit rows</th>
                      <th className="px-3 py-2 font-label-caps text-right">Δ findings</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-t border-level-2 bg-level-0">
                      <td className="px-3 py-2 text-primary">now</td>
                      <td className="px-3 py-2 text-right text-on-surface">
                        {now?.findings ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right text-on-surface">
                        {now?.embeddings ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right text-on-surface">
                        {now?.scope_decisions ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right text-on-surface">
                        {now?.audit_log ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right text-outline">—</td>
                    </tr>
                    {OFFSETS.map((mins, i) => {
                      const snap = snapshots[i];
                      return (
                        <tr key={mins} className="border-t border-level-2">
                          <td className="px-3 py-2 text-on-surface-variant">
                            {mins}m ago
                          </td>
                          {snap ? (
                            <>
                              <td className="px-3 py-2 text-right text-on-surface">
                                {snap.findings}
                              </td>
                              <td className="px-3 py-2 text-right text-on-surface">
                                {snap.embeddings}
                              </td>
                              <td className="px-3 py-2 text-right text-on-surface">
                                {snap.scope_decisions}
                              </td>
                              <td className="px-3 py-2 text-right text-on-surface">
                                {snap.audit_log}
                              </td>
                              <td className="px-3 py-2 text-right text-primary">
                                +{(now?.findings ?? 0) - snap.findings}
                              </td>
                            </>
                          ) : (
                            <td colSpan={5} className="px-3 py-2 text-outline">
                              outside the cluster&apos;s garbage-collection window
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Correlation */}
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="lan" className="text-secondary text-sm" />
                Cross-Target Correlation
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {correlations ? `${correlations.length} shared` : "unreachable"}
              </span>
            </div>
            {!correlations ? (
              <MemoryUnavailable what="correlations" />
            ) : correlations.length === 0 ? (
              <NoRowsYet
                what="shared exposure"
                hint="Correlation needs at least two targets holding the same bytes or reaching the same conclusion."
              />
            ) : (
              <div className="divide-y divide-level-2">
                {correlations.map((c) => (
                  <div key={`${c.kind}:${c.key}`} className="p-panel_padding">
                    <div className="flex items-start gap-3 flex-wrap">
                      <span
                        className={`border px-1.5 py-0.5 rounded text-[10px] uppercase font-data-mono ${
                          c.kind === "artifact"
                            ? "text-secondary border-secondary"
                            : "text-primary border-primary-container"
                        }`}
                      >
                        {c.kind}
                      </span>
                      <span className="font-data-mono-bold text-data-mono-bold text-on-surface break-all">
                        {c.kind === "artifact" ? `${c.key.slice(0, 24)}…` : c.key}
                      </span>
                    </div>
                    <div className="font-data-mono text-data-mono text-on-surface-variant mt-1">
                      {c.detail}
                    </div>
                    <div className="flex gap-2 mt-2 flex-wrap">
                      {c.targets.map((t) => (
                        <span
                          key={t}
                          className="font-data-mono text-[10px] text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="px-panel_padding py-3 border-t border-level-2 font-data-mono text-data-mono text-outline">
              Neither scan can know a file is shared — each only ever sees one estate.
              Only memory, joining on the content address, can.
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-gutter">
            {/* Regressions */}
            <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
              <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
                <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                  <Icon name="warning" className="text-error text-sm" />
                  Regressions
                </h2>
                <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                  {scored ? `${regressed.length}` : "unreachable"}
                </span>
              </div>
              {!scored ? (
                <MemoryUnavailable what="finding status" />
              ) : regressed.length === 0 ? (
                <NoRowsYet
                  what="regressions"
                  hint="Nothing that was fixed has come back. That is the good outcome."
                />
              ) : (
                <div className="divide-y divide-level-2">
                  {regressed.map((f) => (
                    <div key={f.id} className="p-panel_padding">
                      <div className="font-data-mono-bold text-data-mono-bold text-error">
                        {f.title}
                      </div>
                      <div className="font-data-mono text-data-mono text-on-surface-variant mt-1">
                        Recorded fixed, then observed again — came back{" "}
                        {f.regression_count}×. A fix that does not hold is a process
                        problem, and only memory can tell you it happened.
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Decay */}
            <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
              <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
                <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                  <Icon name="trip_origin" className="text-secondary text-sm" />
                  Confidence Decay
                </h2>
                <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                  14-day half-life
                </span>
              </div>
              {!scored ? (
                <MemoryUnavailable what="confidence" />
              ) : scored.length === 0 ? (
                <NoRowsYet what="findings" />
              ) : (
                <div className="p-panel_padding space-y-1 font-data-mono text-data-mono max-h-80 overflow-y-auto">
                  {scored.slice(0, 14).map((f) => (
                    <div key={f.id} className="flex items-center gap-3">
                      <span className="text-on-surface-variant w-12 shrink-0">
                        {f.confidence.toFixed(3)}
                      </span>
                      <span className="h-1.5 w-24 bg-surface-bright rounded overflow-hidden shrink-0">
                        <span
                          className={`block h-full ${
                            f.confidence > 0.7
                              ? "bg-primary"
                              : f.confidence > 0.3
                                ? "bg-secondary"
                                : "bg-error"
                          }`}
                          style={{ width: `${f.confidence * 100}%` }}
                        />
                      </span>
                      <span
                        className={`text-[10px] uppercase w-16 shrink-0 ${
                          f.status === "regressed"
                            ? "text-error"
                            : f.status === "fixed"
                              ? "text-outline"
                              : "text-primary-fixed-dim"
                        }`}
                      >
                        {f.status}
                      </span>
                      <span className="text-on-surface truncate">{f.title}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="px-panel_padding py-3 border-t border-level-2 font-data-mono text-data-mono text-outline">
                Confidence decays from{" "}
                <span className="text-secondary">last_confirmed_at</span>, not from
                when the row was written — so re-confirming a finding restores full
                trust. {stale.length} below 0.5.
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
