import { Icon } from "@/components/Icon";
import { ReactNode } from "react";

export function TopAppBar({
  subtitle,
  cost = "$0.0142 · 340ms avg",
  right,
}: {
  subtitle?: ReactNode;
  cost?: string;
  right?: ReactNode;
}) {
  return (
    <header className="h-top_bar_height w-full bg-surface border-b border-outline-variant flex items-center justify-between px-panel_padding sticky top-0 z-30 shrink-0">
      <div className="flex items-center gap-4">
        <h1 className="font-display-id text-display-id tracking-tighter text-primary">MNEMOS</h1>
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
        <div className="font-data-mono text-data-mono text-primary bg-primary/10 px-3 py-1 rounded border border-primary/20 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          {cost}
        </div>
        {right ?? (
          <button
            aria-label="Live telemetry"
            className="text-on-surface-variant hover:text-primary transition-colors p-2 rounded hover:bg-surface-container-highest"
          >
            <Icon name="sensors" />
          </button>
        )}
      </div>
    </header>
  );
}
