import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getScope } from "@/lib/memory";

export const dynamic = "force-dynamic";

export default async function ScopePage() {
  const rules = await getScope();
  const allows = rules?.filter((r) => r.effect === "allow").length ?? 0;
  const denies = rules?.filter((r) => r.effect === "deny").length ?? 0;

  return (
    <>
      <TopAppBar subtitle="/ Scope" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="policy" className="text-primary text-sm" />
                Scope Ledger
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {rules ? `${allows} allow · ${denies} deny` : "unreachable"}
              </span>
            </div>

            {!rules ? (
              <MemoryUnavailable what="scope decisions" />
            ) : rules.length === 0 ? (
              <NoRowsYet
                what="scope rules"
                hint="With no allow rule the agent can do nothing at all — that is the point."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">Effect</th>
                      <th className="px-4 py-2 font-label-caps">Pattern</th>
                      <th className="px-4 py-2 font-label-caps">Target</th>
                      <th className="px-4 py-2 font-label-caps">Reason</th>
                      <th className="px-4 py-2 font-label-caps">Decided by</th>
                      <th className="px-4 py-2 font-label-caps">Decided at</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((r) => (
                      <tr key={r.id} className="border-t border-level-2 hover:bg-level-0">
                        <td className="px-4 py-2 whitespace-nowrap">
                          <span
                            className={`border px-1.5 py-0.5 rounded text-[10px] uppercase ${
                              r.effect === "deny"
                                ? "text-error border-error"
                                : "text-primary border-primary-container"
                            }`}
                          >
                            {r.effect}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-on-surface font-data-mono-bold">
                          {r.pattern}
                        </td>
                        <td className="px-4 py-2 text-on-surface-variant">
                          {r.root_domain ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-on-surface-variant">{r.reason}</td>
                        <td className="px-4 py-2 text-outline">{r.decided_by}</td>
                        <td className="px-4 py-2 text-outline whitespace-nowrap">
                          {new Date(r.decided_at).toISOString().replace("T", " ").slice(0, 19)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="bg-level-1 border border-level-2 rounded shadow p-panel_padding font-data-mono text-data-mono text-on-surface-variant space-y-2">
            <p>
              <span className="text-primary">Deny by default.</span> A host with no
              matching allow rule is refused. An explicit deny always beats a wildcard
              allow.
            </p>
            <p>
              <span className="text-primary">Append only.</span> This table is a ledger,
              not a config file. A scope change is a new row, never a mutation, so
              &ldquo;what were we allowed to do at 14:02?&rdquo; stays answerable. The
              application role has <span className="text-primary">SELECT, INSERT</span>{" "}
              on it and nothing else — CockroachDB rejects an UPDATE or DELETE outright.
            </p>
            <p>
              <span className="text-primary">Fail closed.</span> If this table cannot be
              read, the guard answers &ldquo;deny&rdquo;. A recon agent that assumes yes
              when its memory is down is a liability.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
