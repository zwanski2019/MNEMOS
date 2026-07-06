import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";

const RULES = [
  { effect: "allow", pattern: "^api\\.sandbox-alpha\\.test/v[1-3]/.*$", reason: "Core API discovery scope", ts: "2026-07-04T08:12Z" },
  { effect: "deny", pattern: ".*\\.admin\\.sandbox-alpha\\.test.*", reason: "OOB admin exclusion", ts: "2026-07-04T08:15Z" },
  { effect: "allow", pattern: "10.42.0.0/16", reason: "Primary staging subnet", ts: "2026-07-04T08:22Z" },
  { effect: "deny", pattern: "10.42.0.1", reason: "Staging gateway exclusion", ts: "2026-07-04T08:23Z" },
] as const;

export default function ScopePage() {
  return (
    <>
      <TopAppBar subtitle="Scope Ledger" />
      <main className="flex-1 overflow-y-auto p-gutter bg-pattern flex flex-col gap-gutter">
        <div className="w-full bg-error-container/20 border border-error/50 rounded p-4 flex items-start gap-4">
          <Icon name="gpp_bad" filled className="text-error mt-0.5" />
          <div>
            <h2 className="font-headline-md text-headline-md text-error mb-1">Deny by default — no allow rule, no action.</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              The MNEMOS gateway enforces an implicit deny-all policy. Any host, endpoint, or subnet that does not match an
              active ALLOW rule is rejected at the boundary. Every decision — allow or deny — is written to the audit log.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter flex-1">
          {/* Ledger */}
          <div className="lg:col-span-2 bg-surface-container-low border border-outline-variant rounded flex flex-col overflow-hidden shadow-xl shadow-black/50">
            <div className="p-panel_padding border-b border-outline-variant flex justify-between items-center bg-surface-container">
              <div className="flex items-center gap-2">
                <Icon name="list_alt" className="text-on-surface-variant" />
                <h3 className="font-data-mono-bold text-data-mono-bold text-on-surface uppercase tracking-wider">Immutable Ruleset</h3>
              </div>
              <span className="px-2 py-1 text-[10px] font-data-mono bg-surface-bright border border-outline-variant text-on-surface-variant rounded">TARGET: SANDBOX-ALPHA</span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-tight_stack">
              <div className="grid grid-cols-12 gap-2 px-3 py-2 font-label-caps text-label-caps text-on-surface-variant border-b border-outline-variant/50 sticky top-0 bg-surface-container-low z-10">
                <div className="col-span-2">VERDICT</div>
                <div className="col-span-4">PATTERN (REGEX/CIDR)</div>
                <div className="col-span-4">JUSTIFICATION</div>
                <div className="col-span-2 text-right">TIMESTAMP</div>
              </div>
              {RULES.map((r, i) => (
                <div
                  key={i}
                  className={
                    "grid grid-cols-12 gap-2 px-3 py-2 items-center font-data-mono text-data-mono border-l-2 border-l-transparent transition-all " +
                    (r.effect === "allow" ? "bg-surface-container hover:border-l-primary" : "bg-surface hover:border-l-error")
                  }
                >
                  <div className="col-span-2">
                    <span className={"px-2 py-0.5 rounded text-[11px] font-bold uppercase " + (r.effect === "allow" ? "bg-primary/10 text-primary border border-primary/20" : "bg-error/10 text-error border border-error/20")}>{r.effect}</span>
                  </div>
                  <div className="col-span-4 text-on-surface truncate" title={r.pattern}>{r.pattern}</div>
                  <div className="col-span-4 text-on-surface-variant text-[11px] truncate">{r.reason}</div>
                  <div className="col-span-2 text-right text-on-surface-variant text-[11px]">{r.ts}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Live evaluator */}
          <div className="bg-surface-container-low border border-outline-variant rounded flex flex-col shadow-xl shadow-black/50">
            <div className="p-panel_padding border-b border-outline-variant flex items-center gap-2 bg-surface-container">
              <Icon name="terminal" className="text-primary" />
              <h3 className="font-data-mono-bold text-data-mono-bold text-on-surface uppercase tracking-wider">Live Evaluator</h3>
            </div>
            <div className="p-panel_padding flex flex-col gap-6 flex-1">
              <label className="block">
                <span className="font-label-caps text-label-caps text-on-surface-variant mb-2 block">TEST HOST / IP / URI</span>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-primary font-data-mono">&gt;</span>
                  <input className="w-full bg-surface border border-outline-variant text-on-surface font-data-mono text-data-mono p-2 pl-8 rounded focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all" defaultValue="api.sandbox-alpha.test/v2/users" />
                </div>
              </label>
              <div className="flex-1 bg-surface border border-outline-variant rounded p-4 flex flex-col justify-center items-center relative overflow-hidden">
                <Icon name="policy" className="absolute text-[120px] opacity-5 pointer-events-none" />
                <div className="z-10 flex flex-col items-center text-center">
                  <div className="w-16 h-16 rounded-full bg-primary/10 border-2 border-primary flex items-center justify-center mb-4">
                    <Icon name="check_circle" filled className="text-primary text-3xl" />
                  </div>
                  <h4 className="font-display-id text-display-id text-primary mb-1">ALLOWED</h4>
                  <p className="font-data-mono text-data-mono text-on-surface-variant text-[11px]">Matched: ^api\.sandbox-alpha\.test/v[1-3]/.*$</p>
                </div>
              </div>
              <div className="text-[10px] font-data-mono text-on-surface-variant text-center opacity-70">
                Evaluation latency: 1.2ms · fail-closed
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
