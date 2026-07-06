"use client";

import { Icon } from "@/components/Icon";
import { useState } from "react";
import { TopAppBar } from "@/components/TopAppBar";

type Sev = "CRITICAL" | "HIGH" | "TRIAGE" | "INFO";

type LineageEvent = { ts: string; path: string; confidence: string; strong?: boolean };
type Finding = {
  id: string;
  sev: Sev;
  title: string;
  category: string;
  detected: string;
  insight: string;
  evidence: string;
  lineage?: { merged: number; correlation: string; events: LineageEvent[] };
};

const SEV_STYLES: Record<Sev, string> = {
  CRITICAL: "bg-error/20 text-error border-error/50",
  HIGH: "bg-error/15 text-error border-error/30",
  TRIAGE: "bg-secondary/15 text-secondary border-secondary/30",
  INFO: "bg-on-surface-variant/15 text-on-surface-variant border-on-surface-variant/30",
};

const FINDINGS: Finding[] = [
  {
    id: "FND-001",
    sev: "CRITICAL",
    title: "Exposed Credentials in S3 Bucket",
    category: "Cloud Security",
    detected: "14:22:05.112",
    insight:
      "AWS Access Key found in plaintext within a public bucket. Two access events were merged by the memory layer — same source IP and signature within a 10s window.",
    evidence: `{
  "event_source": "aws:cloudtrail",
  "event_name": "GetObject",
  "source_ip": "192.168.1.45",
  "bucket": "sandbox-alpha-backups",
  "key": "config/prod_env_vars.json",
  "matched_signatures": ["AWS-004-Exposed-Creds", "S3-Public-Read"],
  "artifacts": [{ "type": "AWS_ACCESS_KEY_ID", "obfuscated": true }]
}`,
    lineage: {
      merged: 2,
      correlation: "Same source IP (192.168.1.45) + User-Agent within a 10s sliding window; artifact signature [AWS_ACCESS_KEY_ID].",
      events: [
        { ts: "14:22:05.112", path: "s3://sandbox-alpha-backups/config/prod_env_vars.json", confidence: "98% MATCH", strong: true },
        { ts: "14:21:58.045", path: "s3://sandbox-alpha-backups/logs/access_keys.bak", confidence: "94% MATCH" },
      ],
    },
  },
  {
    id: "FND-002",
    sev: "TRIAGE",
    title: "Anomalous API Access Pattern",
    category: "IAM",
    detected: "14:15:33.901",
    insight:
      "Multiple admin roles accessed outside normal hours from an unrecognized workstation. Correlated with FND-001 credential leakage.",
    evidence: `{
  "event_source": "aws:iam",
  "actor": "svc_export",
  "action": "AssumeRole",
  "resource": "arn:aws:iam::…:role/admin_access",
  "mfa_authenticated": false,
  "api_call_sequence": ["ListRoles", "GetRole", "AssumeRole"],
  "userAgent": "python-requests/2.31.0"
}`,
    lineage: {
      merged: 2,
      correlation: "Events matched via actor id (svc_export) and unusual API call sequence.",
      events: [
        { ts: "14:15:33.901", path: "iam://sandbox-alpha/roles/admin_access", confidence: "99% MATCH", strong: true },
        { ts: "14:12:05.442", path: "iam://sandbox-alpha/policies/global_read", confidence: "91% MATCH" },
      ],
    },
  },
  {
    id: "FND-003",
    sev: "INFO",
    title: "Outdated TLS Certificate Detected",
    category: "Infrastructure",
    detected: "13:45:10.005",
    insight: "Certificate valid but nearing expiry; informational only, no exploit path.",
    evidence: `{ "issuer": "Let's Encrypt", "not_after": "2026-08-01", "host": "api.sandbox-alpha.test" }`,
  },
  {
    id: "FND-004",
    sev: "TRIAGE",
    title: "Unusual Internal Port Scans",
    category: "Network",
    detected: "12:10:05.442",
    insight: "Sequential port sweep from a single host preceding the credential access.",
    evidence: `{ "src": "10.0.4.22", "ports": [22, 80, 443, 3389], "rate": "45/s" }`,
  },
];

export default function FindingsPage() {
  const [selectedId, setSelectedId] = useState("FND-001");
  const [openLineage, setOpenLineage] = useState<Record<string, boolean>>({ "FND-001": true });
  const selected = FINDINGS.find((f) => f.id === selectedId)!;

  return (
    <>
      <TopAppBar subtitle="TRG: SANDBOX-ALPHA · Findings" />
      <main className="flex-1 overflow-hidden flex flex-col p-panel_padding gap-gutter bg-surface-container-lowest">
        <div className="flex justify-between items-end border-b border-outline-variant pb-4">
          <div>
            <h1 className="font-headline-md text-headline-md text-on-surface mb-1">Findings Report</h1>
            <p className="font-data-mono text-data-mono text-on-surface-variant">Generated: 2026-07-05T14:32:01Z</p>
          </div>
          <div className="flex gap-2">
            <button className="bg-surface-container px-3 py-1.5 rounded border border-outline-variant font-label-caps text-label-caps text-on-surface hover:bg-surface-container-high transition-colors flex items-center gap-2"><Icon name="filter_list" className="text-[16px]" /> FILTER</button>
            <button className="bg-surface-container px-3 py-1.5 rounded border border-outline-variant font-label-caps text-label-caps text-primary hover:bg-surface-container-high transition-colors flex items-center gap-2"><Icon name="download" className="text-[16px]" /> EXPORT</button>
          </div>
        </div>

        <div className="flex-1 flex gap-gutter overflow-hidden">
          {/* List */}
          <div className="w-3/5 bg-surface-container border border-outline-variant rounded flex flex-col overflow-hidden">
            <div className="grid grid-cols-[90px_100px_1fr_130px_150px] gap-4 p-3 bg-surface-container-high border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant sticky top-0 z-10">
              <div>ID</div><div>SEVERITY</div><div>FINDING NAME</div><div>CATEGORY</div><div>DETECTED (UTC)</div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {FINDINGS.map((f) => {
                const active = f.id === selectedId;
                const open = !!openLineage[f.id];
                return (
                  <div key={f.id}>
                    <div
                      onClick={() => setSelectedId(f.id)}
                      className={
                        "grid grid-cols-[90px_100px_1fr_130px_150px] gap-4 p-3 border-b border-outline-variant cursor-pointer font-data-mono text-data-mono transition-colors border-l-2 " +
                        (active ? "bg-surface-container-highest border-l-primary" : "border-l-transparent hover:bg-surface-container-highest hover:border-l-primary/50")
                      }
                    >
                      <div className="text-on-surface">{f.id}</div>
                      <div><span className={`px-2 py-0.5 rounded border font-label-caps text-label-caps ${SEV_STYLES[f.sev]}`}>{f.sev}</span></div>
                      <div className="text-on-surface font-data-mono-bold truncate">{f.title}</div>
                      <div className="text-on-surface-variant truncate">{f.category}</div>
                      <div className="text-on-surface-variant">{f.detected}</div>
                    </div>

                    {f.lineage ? (
                      <div className="pl-8 pr-3 py-3 border-b border-outline-variant bg-surface-container-lowest/50 font-data-mono text-data-mono text-on-surface-variant flex flex-col gap-3">
                        <div className="flex items-center gap-3">
                          <Icon name="subdirectory_arrow_right" className="text-[16px] text-outline" />
                          <span className="text-primary font-label-caps text-label-caps border border-primary/30 bg-primary/10 px-1 rounded">DEDUP</span>
                          <span>Merged from {f.lineage.merged} related events</span>
                          <button
                            onClick={() => setOpenLineage((s) => ({ ...s, [f.id]: !open }))}
                            className="ml-auto text-primary hover:underline font-label-caps text-label-caps flex items-center gap-1"
                          >
                            {open ? "COLLAPSE" : "VIEW"} LINEAGE
                            <Icon name={open ? "expand_less" : "expand_more"} className="text-[14px]" />
                          </button>
                        </div>
                        {open ? (
                          <>
                            <div className="ml-6 border border-outline-variant rounded overflow-hidden">
                              <div className="grid grid-cols-[120px_1fr_100px] gap-4 p-2 bg-surface-container-low border-b border-outline-variant text-[11px] font-label-caps">
                                <div>TIMESTAMP</div><div>RESOURCE PATH</div><div className="text-right">CONFIDENCE</div>
                              </div>
                              {f.lineage.events.map((e, i) => (
                                <div key={i} className={"grid grid-cols-[120px_1fr_100px] gap-4 p-2 border-b border-outline-variant/30 last:border-0 " + (e.strong ? "bg-primary/5" : "")}>
                                  <div className="text-on-surface">{e.ts}</div>
                                  <div className="truncate">{e.path}</div>
                                  <div className={"text-right " + (e.strong ? "text-primary" : "text-secondary")}>{e.confidence}</div>
                                </div>
                              ))}
                            </div>
                            <div className="ml-6 p-3 bg-surface-container-highest/30 border-l-2 border-primary rounded-r flex gap-3">
                              <Icon name="info" className="text-primary text-[18px]" />
                              <div className="text-[12px]">
                                <span className="font-label-caps text-primary block mb-1">CORRELATION LOG</span>
                                <p className="leading-tight">{f.lineage.correlation}</p>
                              </div>
                            </div>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Evidence */}
          <div className="w-2/5 bg-surface-container border border-outline-variant rounded flex flex-col overflow-hidden">
            <div className="p-3 bg-surface-container-high border-b border-outline-variant flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <Icon name="code" className="text-primary text-[18px]" />
                <span className="font-label-caps text-label-caps text-on-surface">EVIDENCE VIEWER</span>
              </div>
              <span className="font-data-mono text-data-mono text-on-surface-variant">{selected.id}</span>
            </div>
            <div className="bg-primary/5 border-b border-primary/20 p-3 shrink-0 flex items-start gap-3">
              <Icon name="smart_toy" className="text-primary mt-0.5" />
              <div>
                <span className="font-label-caps text-label-caps text-primary block mb-1">AGENT INSIGHT</span>
                <p className="font-body-sm text-body-sm text-on-surface-variant">{selected.insight}</p>
              </div>
            </div>
            <div className="flex-1 overflow-auto bg-level-0 p-4">
              <pre className="font-data-mono text-data-mono text-on-surface-variant whitespace-pre-wrap leading-relaxed"><code>{selected.evidence}</code></pre>
            </div>
          </div>
        </div>

        <footer className="h-8 border-t border-outline-variant flex items-center justify-between px-2 shrink-0 font-label-caps text-label-caps text-on-surface-variant">
          <div className="flex items-center gap-4">
            <span>TOTAL FINDINGS: <strong className="text-on-surface">142</strong></span>
            <span>CRITICAL: <strong className="text-error">12</strong></span>
            <span>TRIAGE: <strong className="text-secondary">45</strong></span>
            <span>DUPLICATES MERGED: <strong className="text-primary">18</strong></span>
          </div>
          <div className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" /> SYNCED: JUST NOW</div>
        </footer>
      </main>
    </>
  );
}
