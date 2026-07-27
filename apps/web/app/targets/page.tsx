import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getTargets } from "@/lib/memory";

export const dynamic = "force-dynamic";

export default async function TargetsPage() {
  const targets = await getTargets();

  return (
    <>
      <TopAppBar subtitle="/ Targets" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="target" className="text-primary text-sm" />
                Targets
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {targets ? `${targets.length} authorised` : "unreachable"}
              </span>
            </div>

            {!targets ? (
              <MemoryUnavailable what="targets" />
            ) : targets.length === 0 ? (
              <NoRowsYet what="targets" />
            ) : (
              <div className="divide-y divide-level-2">
                {targets.map((t) => (
                  <div key={t.id} className="p-panel_padding hover:bg-level-0">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div>
                        <div className="font-headline-md text-headline-md text-on-surface">
                          {t.name}
                        </div>
                        <div className="font-data-mono text-data-mono text-primary mt-0.5">
                          {t.root_domain}
                        </div>
                      </div>
                      <div className="flex gap-6 font-data-mono text-data-mono">
                        <div className="text-right">
                          <div className="text-outline text-[10px] uppercase tracking-widest">
                            Assets
                          </div>
                          <div className="text-on-surface text-lg">{t.asset_count}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-outline text-[10px] uppercase tracking-widest">
                            Findings
                          </div>
                          <div className="text-primary text-lg">{t.finding_count}</div>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 font-data-mono text-data-mono text-on-surface-variant border-l-2 border-secondary pl-3">
                      <span className="text-secondary uppercase text-[10px] tracking-widest block">
                        Authorisation on record
                      </span>
                      {t.authorisation}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="font-data-mono text-data-mono text-outline px-1">
            A target and its scope rules are written in one transaction. A target that
            existed without its rules would be one the guard cannot reason about — and
            no rule means deny, so a partial write would silently disable the agent.
            Creating a target with no allow rule is refused outright.
          </p>
        </div>
      </div>
    </>
  );
}
