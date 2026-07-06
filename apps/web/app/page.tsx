import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";

export default function OverviewPage() {
  return (
    <>
      <TopAppBar subtitle="/ Overview" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          {/* Stat cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
            <StatCard title="Active Targets" icon="target" iconClass="text-primary-container" value="14"
              foot={<span className="text-primary-fixed-dim flex items-center gap-1"><Icon name="arrow_upward" className="text-[10px]" />+2 since 00:00 UTC</span>} accent />
            <div className="bg-level-1 border border-level-2 p-panel_padding flex flex-col gap-2 rounded shadow">
              <div className="flex justify-between items-start">
                <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">Findings by State</h2>
                <Icon name="pie_chart" className="text-secondary text-sm" />
              </div>
              <div className="flex gap-1 w-full h-2 mt-2 rounded overflow-hidden">
                <div className="bg-error w-1/5" title="New: 24" />
                <div className="bg-secondary w-2/5" title="Triaged: 48" />
                <div className="bg-primary-container w-[15%]" title="Confirmed: 18" />
                <div className="bg-tertiary-container w-[10%]" title="Reported: 12" />
                <div className="bg-surface-bright w-[15%]" title="Duplicate: 18" />
              </div>
              <div className="font-data-mono text-[10px] text-on-surface-variant mt-auto pt-2 grid grid-cols-3 gap-1">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-error" /> New (24)</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-secondary" /> Tri (48)</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-primary-container" /> Cnf (18)</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-tertiary-container" /> Rep (12)</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-surface-bright" /> Dup (18)</span>
              </div>
            </div>
            <StatCard title="Assets Discovered" icon="lan" iconClass="text-tertiary-container" value="3,492"
              foot={<span>Across 12 subnets</span>} />
            <StatCard title="Total Agent Cost" icon="payments" iconClass="text-outline" value="$142.85"
              foot={<span className="flex items-center gap-2">MTD<span className="h-1 flex-1 bg-surface-bright rounded overflow-hidden inline-block w-16"><span className="block h-full bg-outline w-1/3" /></span></span>} />
          </div>

          {/* Main two-column */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-gutter h-[calc(100vh-220px)] min-h-[500px]">
            {/* Live telemetry */}
            <div className="xl:col-span-2 bg-level-1 border border-level-2 rounded shadow flex flex-col overflow-hidden">
              <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
                <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                  <Icon name="terminal" className="text-primary text-sm" />
                  Live Telemetry Stream
                </h2>
              </div>
              <div className="flex-1 overflow-y-auto font-data-mono text-data-mono bg-level-0 p-2 space-y-tight_stack">
                <LogLine ts="14:22:01.442" tag="scanner" tagClass="text-primary" text="Initiating stealth scan on sandbox-alpha…" ms="12ms" />
                <LogLine ts="14:22:01.890" tag="gateway" tagClass="text-secondary" textClass="text-secondary-fixed-dim" text="Scope check: staging.* denied by rule. Backing off." ms="450ms" />
                <LogLine ts="14:22:02.115" tag="analyst" tagClass="text-tertiary" text="Recall before reason: 3 prior findings pulled from vector memory." ms="88ms" />
                <LogLine ts="14:22:03.001" tag="alert" tagClass="text-on-error" tagBg="bg-error" bold textClass="text-error" text="Dedup: candidate ≈ FIN-9942 (98% sim). Marked duplicate." ms="15ms" />
                <LogLine ts="14:22:03.050" tag="scanner" tagClass="text-primary" text="Fetching JS bundle → S3, metadata → artifacts." ms="49ms" />
                <LogLine ts="14:22:04.221" tag="analyst" tagClass="text-primary" text="Novel finding persisted as confirmed. Audit row written." ms="120ms" />
              </div>
            </div>

            {/* Right column */}
            <div className="flex flex-col gap-gutter">
              <div className="bg-level-1 border border-level-2 rounded shadow p-panel_padding flex flex-col h-1/2">
                <div className="flex justify-between items-center mb-4 border-b border-level-2 pb-2">
                  <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest flex items-center gap-2">
                    <Icon name="history_edu" className="text-sm" />Memory Recall
                  </h2>
                </div>
                <div className="flex-1 flex flex-col gap-3 overflow-y-auto">
                  <RecallCard title="3 findings matched prior sessions" sim="98% SIM" color="text-primary" bar="bg-primary-container" pct="98%"
                    desc="Target profile matches behavior observed in a prior seeded session." />
                  <RecallCard title="Similar TLS cert pattern" sim="82% SIM" color="text-secondary" bar="bg-secondary" pct="82%"
                    desc="Subject DN matches a generic format seen in earlier recon." />
                </div>
              </div>
              <div className="bg-level-1 border border-level-2 rounded shadow p-panel_padding flex flex-col h-1/2 relative overflow-hidden">
                <div className="flex justify-between items-center mb-2 z-10 relative">
                  <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest flex items-center gap-2">
                    <Icon name="public" className="text-sm" />State Distribution
                  </h2>
                  <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">CockroachDB</span>
                </div>
                <div className="flex-1 relative mt-2 bg-surface-container-low border border-level-2 rounded overflow-hidden">
                  <div className="absolute top-[30%] left-[20%] w-2 h-2 rounded-full bg-primary-container animate-ping" />
                  <div className="absolute top-[30%] left-[20%] w-2 h-2 rounded-full bg-primary-container" />
                  <div className="absolute top-[40%] left-[45%] w-1.5 h-1.5 rounded-full bg-secondary animate-ping" style={{ animationDelay: "0.5s" }} />
                  <div className="absolute top-[25%] left-[75%] w-2 h-2 rounded-full bg-primary-container animate-ping" style={{ animationDelay: "1s" }} />
                  <div className="absolute bottom-2 left-2 text-[10px] font-data-mono text-primary-fixed-dim bg-surface-container px-1 border border-level-2 rounded opacity-80">
                    Syncing: US-East · EU-West · AP-Northeast
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function StatCard({ title, icon, iconClass, value, foot, accent }: {
  title: string; icon: string; iconClass: string; value: string; foot: React.ReactNode; accent?: boolean;
}) {
  return (
    <div className="bg-level-1 border border-level-2 p-panel_padding flex flex-col gap-2 rounded shadow relative overflow-hidden group hover:border-outline-variant transition-colors">
      {accent ? <div className="absolute top-0 left-0 w-1 h-full bg-primary-container opacity-50 group-hover:opacity-100 transition-opacity" /> : null}
      <div className="flex justify-between items-start">
        <h2 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">{title}</h2>
        <Icon name={icon} className={`text-sm ${iconClass}`} />
      </div>
      <div className="font-display-id text-display-id text-on-surface">{value}</div>
      <div className="font-data-mono text-data-mono text-on-surface-variant text-xs mt-auto">{foot}</div>
    </div>
  );
}

function LogLine({ ts, tag, tagClass, tagBg = "bg-surface-bright", text, textClass = "text-on-surface-variant", ms, bold }: {
  ts: string; tag: string; tagClass: string; tagBg?: string; text: string; textClass?: string; ms: string; bold?: boolean;
}) {
  return (
    <div className="group flex items-start gap-3 py-1 px-2 hover:bg-level-1 border-l-2 border-transparent hover:border-primary-container transition-colors">
      <span className="text-outline shrink-0 whitespace-nowrap">{ts}</span>
      <span className={`${tagBg} ${tagClass} px-1 rounded text-xs shrink-0 ${bold ? "font-data-mono-bold" : ""}`}>[{tag}]</span>
      <span className={`${textClass} flex-1 break-all ${bold ? "font-data-mono-bold" : ""}`}>{text}</span>
      <span className="text-outline text-xs shrink-0">{ms}</span>
    </div>
  );
}

function RecallCard({ title, sim, color, bar, pct, desc }: {
  title: string; sim: string; color: string; bar: string; pct: string; desc: string;
}) {
  return (
    <div className="bg-surface-container-low p-3 border border-level-2 rounded hover:border-outline-variant transition-colors cursor-pointer">
      <div className="flex justify-between items-start mb-1">
        <span className={`font-data-mono-bold text-data-mono-bold text-sm ${color}`}>{title}</span>
        <span className="text-xs text-outline font-data-mono">{sim}</span>
      </div>
      <div className="text-xs text-on-surface-variant mb-2">{desc}</div>
      <div className="h-1 w-full bg-surface-bright rounded overflow-hidden flex">
        <div className={`h-full ${bar}`} style={{ width: pct }} />
      </div>
    </div>
  );
}
