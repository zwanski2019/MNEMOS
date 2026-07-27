import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getAudit } from "@/lib/memory";

export const dynamic = "force-dynamic";

const ACTOR_CLASS: Record<string, string> = {
  scanner: "text-primary",
  gateway: "text-secondary",
  analyst: "text-tertiary",
  operator: "text-on-surface-variant",
};

const DECISION_CLASS: Record<string, string> = {
  deny: "text-error border-error",
  allow: "text-primary border-primary-container",
  hit: "text-secondary border-secondary",
  miss: "text-outline border-outline-variant",
  ok: "text-primary-fixed-dim border-outline-variant",
};

export default async function AuditPage() {
  const rows = await getAudit(200);
  const denials = rows?.filter((r) => r.decision === "deny").length ?? 0;

  return (
    <>
      <TopAppBar subtitle="/ Audit" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="history" className="text-primary text-sm" />
                Audit Log
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {rows ? `${rows.length} rows · ${denials} denials` : "unreachable"}
              </span>
            </div>

            {!rows ? (
              <MemoryUnavailable what="the audit log" />
            ) : rows.length === 0 ? (
              <NoRowsYet what="audit rows" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">Time</th>
                      <th className="px-4 py-2 font-label-caps">Actor</th>
                      <th className="px-4 py-2 font-label-caps">Action</th>
                      <th className="px-4 py-2 font-label-caps">Decision</th>
                      <th className="px-4 py-2 font-label-caps">Resource</th>
                      <th className="px-4 py-2 font-label-caps">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className="border-t border-level-2 hover:bg-level-0">
                        <td className="px-4 py-1.5 text-outline whitespace-nowrap">
                          {new Date(r.at).toISOString().replace("T", " ").slice(0, 23)}
                        </td>
                        <td
                          className={`px-4 py-1.5 whitespace-nowrap ${ACTOR_CLASS[r.actor] ?? "text-on-surface"}`}
                        >
                          {r.actor}
                        </td>
                        <td className="px-4 py-1.5 text-on-surface whitespace-nowrap">
                          {r.action}
                        </td>
                        <td className="px-4 py-1.5 whitespace-nowrap">
                          <span
                            className={`border px-1.5 py-0.5 rounded text-[10px] uppercase ${
                              DECISION_CLASS[r.decision] ?? "text-outline border-outline-variant"
                            }`}
                          >
                            {r.decision}
                          </span>
                        </td>
                        <td className="px-4 py-1.5 text-on-surface-variant max-w-xs truncate">
                          {r.resource ?? "—"}
                        </td>
                        <td className="px-4 py-1.5 text-outline text-[10px] max-w-sm truncate">
                          {JSON.stringify(r.detail)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="font-data-mono text-data-mono text-outline px-1">
            This table is append-only, enforced by CockroachDB: the application role
            holds <span className="text-primary">SELECT, INSERT</span> on{" "}
            <span className="text-primary">audit_log</span> and nothing else. Rows
            cannot be rewritten or erased, even with the application&apos;s own
            credentials.
          </p>
        </div>
      </div>
    </>
  );
}
