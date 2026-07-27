import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getFindings } from "@/lib/memory";

export const dynamic = "force-dynamic";

const SEVERITY_CLASS: Record<string, string> = {
  critical: "text-error border-error",
  high: "text-secondary border-secondary",
  medium: "text-primary-container border-primary-container",
  low: "text-tertiary-container border-tertiary-container",
  info: "text-outline border-outline-variant",
};

export default async function FindingsPage() {
  const findings = await getFindings(100);

  return (
    <>
      <TopAppBar subtitle="/ Findings" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="search_check" className="text-primary text-sm" />
                Findings
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {findings ? `${findings.length} rows · findings table` : "unreachable"}
              </span>
            </div>

            {!findings ? (
              <MemoryUnavailable what="findings" />
            ) : findings.length === 0 ? (
              <NoRowsYet what="findings" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">Severity</th>
                      <th className="px-4 py-2 font-label-caps">Title</th>
                      <th className="px-4 py-2 font-label-caps">Target</th>
                      <th className="px-4 py-2 font-label-caps text-right">Seen</th>
                      <th className="px-4 py-2 font-label-caps">First written</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f) => (
                      <tr
                        key={f.id}
                        className="border-t border-level-2 hover:bg-level-0 align-top"
                      >
                        <td className="px-4 py-2 whitespace-nowrap">
                          <span
                            className={`border px-1.5 py-0.5 rounded text-[10px] uppercase ${
                              SEVERITY_CLASS[f.severity] ?? "text-outline border-outline-variant"
                            }`}
                          >
                            {f.severity}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-on-surface max-w-md">
                          <div className="font-data-mono-bold">{f.title}</div>
                          <div className="text-on-surface-variant text-xs mt-0.5">
                            {f.summary}
                          </div>
                        </td>
                        <td className="px-4 py-2 text-on-surface-variant whitespace-nowrap">
                          {f.root_domain ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-right whitespace-nowrap">
                          <span
                            className={
                              f.times_seen > 1 ? "text-secondary" : "text-on-surface-variant"
                            }
                          >
                            {f.times_seen}×
                          </span>
                        </td>
                        <td className="px-4 py-2 text-outline whitespace-nowrap">
                          {new Date(f.created_at).toISOString().replace("T", " ").slice(0, 19)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="font-data-mono text-data-mono text-outline px-1">
            Every row here survived a fail-closed scope check and a vector-similarity
            dedup pass. A finding seen more than once was recognised from memory and
            never written twice.
          </p>
        </div>
      </div>
    </>
  );
}
