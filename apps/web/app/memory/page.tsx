import { Icon } from "@/components/Icon";
import { TopAppBar } from "@/components/TopAppBar";
import { MemoryUnavailable, NoRowsYet } from "@/components/Empty";
import { getArtifacts, getEmbeddings, getStats } from "@/lib/memory";

export const dynamic = "force-dynamic";

export default async function MemoryPage() {
  const [stats, chunks, artifacts] = await Promise.all([
    getStats(),
    getEmbeddings(30),
    getArtifacts(30),
  ]);

  return (
    <>
      <TopAppBar subtitle="/ Memory" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-[2560px] mx-auto space-y-gutter">
          {/* What the vector index holds */}
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="memory" className="text-primary text-sm" />
                Indexed Chunks
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                {stats
                  ? `${stats.embeddings} vectors · embeddings_vec`
                  : "unreachable"}
              </span>
            </div>

            {!chunks ? (
              <MemoryUnavailable what="indexed chunks" />
            ) : chunks.length === 0 ? (
              <NoRowsYet what="chunks" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">Target</th>
                      <th className="px-4 py-2 font-label-caps">Chunk</th>
                      <th className="px-4 py-2 font-label-caps">Content</th>
                      <th className="px-4 py-2 font-label-caps">Embedding model</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chunks.map((c) => (
                      <tr key={c.id} className="border-t border-level-2 hover:bg-level-0">
                        <td className="px-4 py-2 text-on-surface-variant whitespace-nowrap">
                          {c.root_domain ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-outline">#{c.chunk_idx}</td>
                        <td className="px-4 py-2 text-on-surface max-w-xl truncate">
                          {c.content.replace(/\s+/g, " ").trim()}
                        </td>
                        <td className="px-4 py-2 text-outline whitespace-nowrap">
                          {c.model}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* S3 artifacts */}
          <div className="bg-level-1 border border-level-2 rounded shadow overflow-hidden">
            <div className="border-b border-level-2 px-panel_padding py-3 flex justify-between items-center bg-surface-container-low">
              <h2 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                <Icon name="cloud" className="text-secondary text-sm" />
                Artifacts
              </h2>
              <span className="text-[10px] font-data-mono text-outline border border-outline-variant px-1 rounded bg-surface">
                bytes in Amazon S3 · addresses here
              </span>
            </div>

            {!artifacts ? (
              <MemoryUnavailable what="artifacts" />
            ) : artifacts.length === 0 ? (
              <NoRowsYet what="artifacts" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-data-mono text-data-mono">
                  <thead className="bg-surface-container-low text-on-surface-variant">
                    <tr className="text-left uppercase text-[10px] tracking-widest">
                      <th className="px-4 py-2 font-label-caps">sha256</th>
                      <th className="px-4 py-2 font-label-caps text-right">Bytes</th>
                      <th className="px-4 py-2 font-label-caps">Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {artifacts.map((a) => (
                      <tr
                        key={a.sha256}
                        className="border-t border-level-2 hover:bg-level-0"
                      >
                        <td className="px-4 py-2 text-primary whitespace-nowrap">
                          {a.sha256.slice(0, 16)}…
                        </td>
                        <td className="px-4 py-2 text-right text-on-surface-variant">
                          {a.byte_len.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-outline break-all">
                          {a.s3_bucket ? (
                            <>
                              <span className="text-secondary">s3://{a.s3_bucket}/</span>
                              {a.s3_key}
                            </>
                          ) : (
                            <span className="text-outline">
                              {a.s3_key}{" "}
                              <span className="text-error">(not uploaded)</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="font-data-mono text-data-mono text-outline px-1">
            Chunks are embedded at 1024 dimensions and stored behind CockroachDB&apos;s
            distributed vector index. That index carries two load-bearing paths:
            cross-session <span className="text-primary">recall</span> before the
            analyst reasons, and <span className="text-secondary">dedup</span> before
            the gateway writes. Artifact keys are content-addressed, so the same bundle
            served from ten hosts is stored once.
          </p>
        </div>
      </div>
    </>
  );
}
