import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";

export default function LiveRunsPage() {
  return (
    <>
      <TopAppBar
        subtitle="TARGET: SANDBOX-ALPHA"
        right={
          <button aria-label="Live telemetry" className="text-on-surface-variant hover:text-primary transition-colors p-2 rounded hover:bg-surface-container-highest">
            <Icon name="sensors" />
          </button>
        }
      />
      <main className="flex-1 overflow-y-auto p-gutter flex flex-col gap-gutter">
        <div className="flex justify-between items-end mb-2">
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface">Agent Execution Stream</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">CYCLE-ID: 88A4-B92</p>
          </div>
          <button className="bg-level-1 border border-level-2 hover:bg-surface-container-highest transition-colors px-4 py-2 font-data-mono-bold text-data-mono-bold text-on-surface flex items-center gap-2 rounded">
            <Icon name="pause" className="text-[16px]" />
            HALT EXECUTION
          </button>
        </div>

        <div className="grid grid-cols-12 gap-gutter h-full min-h-0">
          {/* Left: metrics + timeline */}
          <div className="col-span-12 lg:col-span-8 flex flex-col gap-gutter h-full">
            <div className="bg-level-1 border border-level-2 p-panel_padding rounded flex justify-between items-center shadow-lg">
              <div className="flex gap-6">
                <Metric label="Current Phase" value="ANALYZE" valueClass="text-primary" />
                <Metric label="Tokens Consumed" value="14,208" />
                <Metric label="Cost Ceiling" value="$2.50 / $5.00" valueClass="text-error" />
              </div>
              <div className="w-64">
                <div className="flex justify-between font-label-caps text-label-caps text-on-surface-variant mb-1">
                  <span>Budget</span><span>50%</span>
                </div>
                <div className="w-full h-1 bg-surface-container-lowest rounded-full overflow-hidden">
                  <div className="h-full bg-primary-container w-1/2" />
                </div>
              </div>
            </div>

            <div className="bg-level-1 border border-level-2 flex-1 rounded p-panel_padding overflow-y-auto">
              <div className="relative pl-6 border-l border-outline-variant space-y-6">
                <Phase state="done" title="Recon" ts="14:02:11.450"
                  lines={["Scanned 4 endpoints.", "Open ports: 22, 80, 443.", "Tokens: 2,140 | Latency: 450ms"]} />
                <Phase state="done" title="Embed" ts="14:02:12.800"
                  lines={["Chunked bundles → Titan V2 embeddings.", "Vector dimension: 1024.", "Tokens: 4,050 | Latency: 820ms"]} />
                <Phase state="active" title="Analyze" ts="14:02:15.112"
                  lines={["Recall before reason complete.", "Reasoning over prior context…", "Context window: 8,018 tokens."]} />
                <Phase state="pending" title="Dedup" />
              </div>
            </div>
          </div>

          {/* Right: recall context */}
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-gutter h-full">
            <div className="bg-level-1 border border-level-2 flex-1 rounded p-panel_padding flex flex-col shadow-lg border-t-2 border-t-secondary-container">
              <div className="flex items-center gap-2 mb-4">
                <Icon name="memory" className="text-secondary text-[20px]" />
                <h3 className="font-headline-md text-headline-md text-secondary">Recall Context</h3>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-4">
                Distributed vector search pulled prior findings before the analyze phase — the memory that makes the run smart.
              </p>
              <div className="space-y-3 flex-1 overflow-y-auto pr-2">
                <RecallItem sim="Sim: 98.4%" ago="-2h 14m" text="Similar SSRF-on-export pattern observed on a prior session (FIN-9942)." thought="Reuse payload; likely duplicate → dedup" />
                <RecallItem sim="Sim: 85.1%" ago="-1d 4h" text="Legacy /v1/auth endpoint merged from an acquisition, never re-secured." thought="Target legacy API surface" />
                <div className="mt-4 p-3 bg-surface-container-lowest border border-outline-variant rounded">
                  <div className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-2">Injected Prompt Payload</div>
                  <div className="font-data-mono text-data-mono text-outline text-xs h-24 overflow-hidden relative">
                    System: You are an autonomous recon analyst. Given recon data [DATA_BLOCK_A] and historical
                    context [VECTOR_RESULTS], decide if this is a novel, in-scope finding.
                    <br />
                    <br />
                    User: Begin analysis.
                    <div className="absolute bottom-0 left-0 w-full h-8 bg-gradient-to-t from-surface-container-lowest to-transparent" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

function Metric({ label, value, valueClass = "text-on-surface" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <div className="font-label-caps text-label-caps text-on-surface-variant uppercase">{label}</div>
      <div className={`font-data-mono-bold text-data-mono-bold mt-1 ${valueClass}`}>{value}</div>
    </div>
  );
}

function Phase({ state, title, ts, lines = [] }: {
  state: "done" | "active" | "pending"; title: string; ts?: string; lines?: string[];
}) {
  if (state === "pending") {
    return (
      <div className="relative opacity-50">
        <div className="absolute -left-[29px] top-1 w-3 h-3 rounded-full bg-surface-container-highest border border-outline-variant" />
        <div className="flex items-center gap-3 mb-2">
          <h3 className="font-headline-md text-headline-md text-on-surface-variant">{title}</h3>
          <span className="font-label-caps text-label-caps px-2 py-0.5 rounded border border-outline-variant text-on-surface-variant uppercase">Pending</span>
        </div>
      </div>
    );
  }
  const active = state === "active";
  return (
    <div className={active ? "relative border-l-2 border-primary-container -ml-[25px] pl-[23px] pb-2" : "relative"}>
      <div className={"absolute top-1 flex items-center justify-center " + (active ? "-left-[9px] w-4 h-4 rounded-full bg-primary-container border-2 border-[#111721]" : "-left-[31px] w-4 h-4 rounded-full bg-surface-container-highest border border-outline-variant")}>
        {active ? <span className="w-1.5 h-1.5 rounded-full bg-[#111721] animate-pulse" /> : <Icon name="check" filled className="text-[12px] text-on-surface-variant" />}
      </div>
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-3">
          <h3 className={"font-headline-md text-headline-md " + (active ? "text-primary" : "text-on-surface-variant")}>{title}</h3>
          {active ? (
            <span className="bg-primary-container/15 text-primary-container border border-primary-container/30 font-label-caps text-label-caps px-2 py-0.5 rounded uppercase flex items-center gap-1">
              <Icon name="sync" className="text-[12px] animate-spin" /> In Progress
            </span>
          ) : (
            <span className="bg-on-surface-variant/10 text-on-surface-variant border border-on-surface-variant/20 font-label-caps text-label-caps px-2 py-0.5 rounded uppercase">Completed</span>
          )}
        </div>
        <span className={"font-data-mono text-data-mono " + (active ? "text-primary animate-pulse" : "text-on-surface-variant")}>{ts}</span>
      </div>
      <div className={"rounded p-3 font-data-mono text-data-mono text-sm " + (active ? "bg-surface-container-low border border-primary-container/30 text-on-surface" : "bg-surface-container-lowest border border-outline-variant text-on-surface-variant")}>
        {lines.map((l, i) => (<div key={i}>&gt; {l}</div>))}
        {active ? (
          <div className="mt-2 w-full h-1 bg-surface-container-highest rounded-full overflow-hidden">
            <div className="h-full bg-primary-container w-[75%]" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RecallItem({ sim, ago, text, thought }: { sim: string; ago: string; text: string; thought?: string }) {
  return (
    <div className="bg-surface-container-low border border-outline-variant rounded p-3 hover:border-secondary transition-colors cursor-pointer group">
      <div className="flex justify-between items-start mb-1">
        <span className="font-data-mono-bold text-data-mono-bold text-on-surface group-hover:text-secondary">{sim}</span>
        <span className="font-data-mono text-data-mono text-on-surface-variant">{ago}</span>
      </div>
      <div className="font-body-sm text-body-sm text-on-surface-variant">{text}</div>
      {thought ? (
        <div className="mt-2 inline-flex items-center gap-1 px-2 py-1 bg-level-0 border border-outline-variant rounded font-data-mono text-[10px] text-primary">
          <Icon name="lightbulb" className="text-[12px]" />
          AGENT THOUGHT: {thought}
        </div>
      ) : null}
    </div>
  );
}
