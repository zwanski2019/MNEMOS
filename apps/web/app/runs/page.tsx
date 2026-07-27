import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getRuns } from "@/lib/memory";

export const dynamic = "force-dynamic";

const STATUS_CLASS: Record<string, string> = {
  complete: "text-primary border-primary-container",
  running: "text-secondary border-secondary",
  halted: "text-error border-error",
  failed: "text-error border-error",
};

export default async function RunsPage() {
  const runs = await getRuns(40);

  return (
    <>
      <TopAppBar subtitle="/ Live Runs" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="play_circle" className="text-primary text-sm" />
                Agent Runs
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {runs ? `${runs.length} rows · agent_runs` : "unreachable"}
              </span>
            </div>

            {!runs ? (
              <MemoryUnavailable what="agent runs" />
            ) : runs.length === 0 ? (
              <NoRowsYet what="runs" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">Run</th>
                      <th className="px-4 py-2 font-label-caps">Pass</th>
                      <th className="px-4 py-2 font-label-caps">Status</th>
                      <th className="px-4 py-2 font-label-caps text-right">Recalled</th>
                      <th className="px-4 py-2 font-label-caps text-right">Deduped</th>
                      <th className="px-4 py-2 font-label-caps text-right">Written</th>
                      <th className="px-4 py-2 font-label-caps text-right">Cost</th>
                      <th className="px-4 py-2 font-label-caps">Models</th>
                      <th className="px-4 py-2 font-label-caps">Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.id} className="border-t border-level-2 hover:bg-level-0">
                        <td className="px-4 py-2 text-outline whitespace-nowrap">
                          {r.id.slice(0, 8)}…
                        </td>
                        <td className="px-4 py-2 text-on-surface">{r.pass_no}</td>
                        <td className="px-4 py-2 whitespace-nowrap">
                          <span
                            className={`border px-1.5 py-0.5 rounded text-[10px] uppercase ${
                              STATUS_CLASS[r.status] ?? "text-outline border-outline-variant"
                            }`}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right text-tertiary">
                          {r.recalled_count}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary">
                          {r.deduped_count}
                        </td>
                        <td className="px-4 py-2 text-right text-primary">
                          {r.written_count}
                        </td>
                        <td className="px-4 py-2 text-right text-on-surface-variant whitespace-nowrap">
                          ${Number(r.cost_usd).toFixed(4)}
                        </td>
                        <td className="px-4 py-2 text-outline text-[10px] whitespace-nowrap">
                          <div>{r.model || "—"}</div>
                          <div>{r.embed_model || "—"}</div>
                        </td>
                        <td className="px-4 py-2 text-outline whitespace-nowrap">
                          {new Date(r.started_at).toISOString().replace("T", " ").slice(0, 19)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="font-data-mono text-data-mono text-outline px-1">
            <span className="text-tertiary">Recalled</span> is prior context pulled from
            the vector index before the analyst was allowed to reason.{" "}
            <span className="text-secondary">Deduped</span> is candidates memory already
            knew, stopped before write. The cost column is what the per-run ceiling is
            enforced against — read from this table, not from a counter in a process.
          </p>
        </div>
      </div>
    </>
  );
}
