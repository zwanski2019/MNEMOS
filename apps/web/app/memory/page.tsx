import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";

// Deterministic pseudo-random so server and client render identical density cells.
function seeded(i: number) {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const SCATTER = [
  { left: "60%", top: "30%", cls: "bg-primary-container text-primary-container", tip: "JWT_SIGN_BYPASS", sim: "0.942" },
  { left: "62%", top: "35%", cls: "bg-primary-container text-primary-container" },
  { left: "58%", top: "28%", cls: "bg-primary-container text-primary-container" },
  { left: "65%", top: "25%", cls: "bg-primary-container text-primary-container opacity-50" },
  { left: "20%", top: "70%", cls: "bg-error text-error", tip: "STORED_XSS_PROFILE", sim: "0.811" },
  { left: "22%", top: "72%", cls: "bg-error text-error" },
  { left: "18%", top: "68%", cls: "bg-error text-error" },
  { left: "80%", top: "80%", cls: "bg-secondary text-secondary" },
  { left: "85%", top: "75%", cls: "bg-secondary text-secondary" },
  { left: "40%", top: "50%", cls: "bg-on-surface text-on-surface" },
  { left: "45%", top: "55%", cls: "bg-on-surface text-on-surface" },
];

export default function MemoryPage() {
  return (
    <>
      <TopAppBar subtitle="/ Memory Vector Index" />
      <main className="flex-1 overflow-hidden flex grid-bg relative">
        {/* Center: vector map */}
        <div className="flex-1 h-full relative flex flex-col p-panel_padding gap-gutter">
          <div className="w-full max-w-3xl mx-auto z-20 mt-4 relative">
            <Icon name="search" className="absolute inset-y-0 left-0 pl-4 flex items-center text-primary text-[20px]" />
            <input
              className="w-full bg-surface-container-low border border-outline-variant text-on-surface font-data-mono text-data-mono py-4 pl-12 pr-16 rounded focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-[0_0_15px_rgba(34,211,238,0.1)] transition-all placeholder:text-on-surface-variant/50"
              placeholder="Search memory space… (e.g. 'SSRF on export endpoint, any target')"
            />
            <span className="absolute inset-y-0 right-0 pr-4 flex items-center font-data-mono-bold text-label-caps text-on-surface-variant">
              <span className="bg-surface-container-highest px-2 py-1 rounded">CMD+K</span>
            </span>
          </div>

          <div className="flex-1 relative mt-4 border border-outline-variant bg-surface-container-lowest/50 rounded overflow-hidden flex flex-col">
            <div className="px-4 py-2 border-b border-outline-variant bg-surface-container-low flex justify-between items-center shrink-0">
              <span className="font-label-caps text-label-caps text-on-surface-variant">2D CLUSTER PROJECTION</span>
              <div className="flex gap-4 font-label-caps text-label-caps text-on-surface-variant">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-error inline-block" /> Injection</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary-container inline-block" /> Auth</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-secondary inline-block" /> Data</span>
              </div>
            </div>
            <div className="flex-1 relative w-full h-full overflow-hidden">
              <div className="absolute inset-0 flex items-center justify-center opacity-20 pointer-events-none">
                <div className="w-full h-px bg-primary" />
                <div className="h-full w-px bg-primary absolute" />
              </div>
              {SCATTER.map((p, i) => (
                <div key={i} className="group absolute" style={{ left: p.left, top: p.top }}>
                  <div className={`w-1.5 h-1.5 rounded-full cursor-pointer transition-transform hover:scale-[2.5] ${p.cls}`} />
                  {p.tip ? (
                    <div className="absolute left-3 -top-2 opacity-0 group-hover:opacity-100 transition-opacity bg-surface-container/90 backdrop-blur border border-outline-variant p-2 rounded z-20 pointer-events-none whitespace-nowrap">
                      <div className="font-data-mono-bold text-data-mono-bold text-primary">{p.tip}</div>
                      <div className="font-data-mono text-[10px] text-on-surface-variant mt-1">Sim: {p.sim}</div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          <div className="h-48 shrink-0 flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant pl-1">NEAREST NEIGHBOR CONTEXT</span>
            <div className="flex-1 overflow-y-auto pr-2 flex flex-col gap-2">
              <NeighborCard icon="token" iconClass="text-primary" title="artifact_chunk: verifyToken()" score="0.942" scoreClass="text-primary bg-primary/10" bar="bg-primary" pct="94.2%"
                snippet="…if (!token) return res.status(401); const v = jwt.verify(token, process.env.SECRET)…" />
              <NeighborCard icon="description" iconClass="text-secondary" title="Finding: JWT 'none' algorithm accepted" score="0.875" scoreClass="text-secondary bg-secondary/10" bar="bg-secondary" pct="87.5%"
                snippet="/api/user/profile accepts JWTs signed with the 'none' algorithm — authentication bypass…" />
            </div>
          </div>
        </div>

        {/* Side panel */}
        <aside className="w-80 border-l border-outline-variant bg-surface-container h-full shrink-0 flex flex-col z-20">
          <div className="p-4 border-b border-outline-variant">
            <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
              <Icon name="memory" className="text-primary" />Index Status
            </h2>
          </div>
          <div className="p-4 flex flex-col gap-6 overflow-y-auto">
            <div className="flex flex-col gap-3">
              <Stat k="TOTAL_EMBEDDINGS" v="1,492,034" />
              <Stat k="DIMENSIONS" v="1024" vClass="text-primary" />
              <Stat k="INDEX_TYPE" v="CRDB_VECTOR" />
              <Stat k="LAST_SYNC" v="12s ago" />
            </div>
            <div className="bg-surface-container-low p-3 rounded border border-outline-variant flex items-start gap-3">
              <div className="mt-1 w-2 h-2 rounded-full bg-primary animate-pulse shrink-0 shadow-[0_0_8px_#22d3ee]" />
              <div>
                <div className="font-label-caps text-label-caps text-primary mb-1">AGENT BRAIN ONLINE</div>
                <p className="font-body-sm text-[12px] text-on-surface-variant leading-tight">
                  Distributed vector index healthy. Recall + dedup served from strongly-consistent memory.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">MEMORY DENSITY</span>
              <div className="h-24 bg-surface-container-lowest border border-outline-variant rounded flex flex-wrap gap-0.5 p-1 content-start">
                {Array.from({ length: 80 }).map((_, i) => {
                  const o = seeded(i);
                  return (
                    <div key={i} className="w-[8%] h-2 rounded-[1px]" style={{ backgroundColor: o > 0.8 ? "#22d3ee" : "#3c494c", opacity: o }} />
                  );
                })}
              </div>
            </div>
          </div>
          <div className="mt-auto p-4 border-t border-outline-variant bg-surface-container-low">
            <button className="w-full bg-transparent border border-primary text-primary hover:bg-primary/10 font-data-mono-bold text-data-mono-bold py-2 rounded transition-colors flex justify-center items-center gap-2">
              <Icon name="sync" className="text-[18px]" /> REINDEX NOW
            </button>
          </div>
        </aside>
      </main>
    </>
  );
}

function Stat({ k, v, vClass = "text-on-surface" }: { k: string; v: string; vClass?: string }) {
  return (
    <div className="flex justify-between items-baseline border-b border-outline-variant/30 pb-1">
      <span className="font-data-mono text-data-mono text-on-surface-variant">{k}</span>
      <span className={`font-data-mono-bold text-data-mono-bold ${vClass}`}>{v}</span>
    </div>
  );
}

function NeighborCard({ icon, iconClass, title, score, scoreClass, bar, pct, snippet }: {
  icon: string; iconClass: string; title: string; score: string; scoreClass: string; bar: string; pct: string; snippet: string;
}) {
  return (
    <div className="bg-surface-container-low border border-outline-variant p-3 flex flex-col gap-2 hover:border-primary/50 transition-colors cursor-pointer">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Icon name={icon} className={`text-[16px] ${iconClass}`} />
          <span className="font-data-mono-bold text-data-mono-bold text-on-surface">{title}</span>
        </div>
        <span className={`font-data-mono text-data-mono px-2 py-0.5 rounded ${scoreClass}`}>{score}</span>
      </div>
      <div className="w-full bg-surface-container-highest h-1 rounded overflow-hidden">
        <div className={`h-full ${bar}`} style={{ width: pct }} />
      </div>
      <div className="font-data-mono text-[11px] text-on-surface-variant truncate">{snippet}</div>
    </div>
  );
}
