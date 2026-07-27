import { Icon } from "@/components/Icon";
import { ReactNode } from "react";
import { getStats, getTotalCost } from "@/lib/memory";

/**
 * The status pill reads real spend and a real row count out of CockroachDB.
 *
 * It used to render a hardcoded "$0.0142 · 340ms avg", which is exactly the kind of
 * detail that makes a dashboard look alive and makes it dishonest. When memory is
 * unreachable it says so rather than showing a comforting number.
 */
export async function TopAppBar({
  subtitle,
  right,
}: {
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  const [cost, stats] = await Promise.all([getTotalCost(), getStats()]);
  const connected = cost !== null && stats !== null;

  return (
    <header className="h-top_bar_height w-full bg-surface border-b border-outline-variant flex items-center justify-between px-panel_padding sticky top-0 z-30 shrink-0">
      <div className="flex items-center gap-4">
        <h1 className="font-display-id text-display-id tracking-tighter text-primary">
          MNEMOS
        </h1>
        {subtitle ? (
          <>
            <div className="h-4 w-px bg-outline-variant mx-2 hidden md:block" />
            <span className="font-data-mono text-data-mono text-on-surface-variant hidden md:block">
              {subtitle}
            </span>
          </>
        ) : null}
      </div>

      <div className="flex items-center gap-4">
        <div
          className={`font-data-mono text-data-mono px-3 py-1 rounded border flex items-center gap-2 ${
            connected
              ? "text-primary bg-primary/10 border-primary/20"
              : "text-error bg-error/10 border-error/20"
          }`}
          title={
            connected
              ? "Total spend summed from agent_runs"
              : "CockroachDB is not reachable from this deployment"
          }
        >
          <span
            className={`w-2 h-2 rounded-full ${connected ? "bg-primary animate-pulse" : "bg-error"}`}
          />
          {connected
            ? `$${cost.toFixed(4)} · ${stats.findings} findings`
            : "memory offline"}
        </div>
        {right ?? (
          <Icon
            name="sensors"
            className={connected ? "text-primary" : "text-outline"}
          />
        )}
      </div>
    </header>
  );
}
