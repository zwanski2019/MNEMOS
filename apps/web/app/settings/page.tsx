import { TopAppBar } from "@/components/TopAppBar";

export default function SettingsPage() {
  return (
    <>
      <TopAppBar subtitle="/ Settings" />
      <div className="flex-1 overflow-y-auto p-gutter">
        <div className="max-w-2xl mx-auto mt-8 bg-level-1 border border-outline-variant rounded p-6 flex flex-col gap-4">
          <h2 className="font-headline-md text-headline-md text-on-surface">Settings</h2>
          <p className="font-body-sm text-on-surface-variant">
            Operator preferences, cost ceilings, and cluster connection status will live here. Placeholder for now —
            wired to the gateway once P2 (scope guard + audit) lands.
          </p>
          <div className="font-data-mono text-data-mono text-on-surface-variant border-t border-outline-variant/40 pt-4">
            <div className="flex justify-between py-1"><span>COST_CEILING_USD</span><span className="text-primary">$5.00 / run</span></div>
            <div className="flex justify-between py-1"><span>CRDB_CLUSTER</span><span className="text-on-surface-variant">not connected</span></div>
            <div className="flex justify-between py-1"><span>BEDROCK_REGION</span><span className="text-on-surface-variant">us-east-1</span></div>
          </div>
        </div>
      </div>
    </>
  );
}
