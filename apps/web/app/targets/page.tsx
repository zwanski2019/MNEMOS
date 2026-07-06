"use client";

import { Icon } from "@/components/Icon";
import { useState } from "react";
import { TopAppBar } from "@/components/TopAppBar";
import { useFocusTrap } from "@/components/useFocusTrap";

type Row = {
  id: string;
  name: string;
  icon: string;
  platform: string;
  assets: string;
  open: number;
  triaged: number;
  last: string;
  status: "Active" | "Paused";
  selected?: boolean;
};

const ROWS: Row[] = [
  { id: "sandbox-alpha", name: "Sandbox Alpha (authorized)", icon: "domain", platform: "BBS", assets: "1,402", open: 3, triaged: 12, last: "2026-07-05 14:32:01", status: "Active", selected: true },
  { id: "beta-systems", name: "Beta Systems Cloud", icon: "cloud", platform: "AWS", assets: "842", open: 1, triaged: 0, last: "2026-07-04 09:12:44", status: "Active" },
  { id: "gamma-corp", name: "Gamma Corp VPN", icon: "vpn_lock", platform: "Azure", assets: "12", open: 0, triaged: 4, last: "2026-07-04 22:05:11", status: "Paused" },
  { id: "delta-x", name: "Delta-X Mainframe", icon: "terminal", platform: "On-Prem", assets: "3,109", open: 12, triaged: 85, last: "2026-07-05 01:15:00", status: "Active" },
];

export default function TargetsPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>(ROWS);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const purge = () => {
    const count = selected.size;
    setRows((r) => r.filter((x) => !selected.has(x.id)));
    setSelected(new Set());
    setDeleteOpen(false);
    setToast(`${count} TARGET${count === 1 ? "" : "S"} PURGED FROM REGISTRY`);
    setTimeout(() => setToast(null), 5000);
  };

  return (
    <>
      <TopAppBar subtitle="/ Targets" />
      <div className="flex-1 overflow-y-auto p-panel_padding lg:p-6 flex flex-col gap-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface">Target Registry</h2>
            <p className="font-data-mono text-data-mono text-on-surface-variant mt-1">
              Active reconnaissance scopes and defined parameters.
            </p>
          </div>
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <Icon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm" />
              <input
                className="w-full bg-surface-container-low border border-outline-variant text-on-surface font-data-mono text-data-mono py-1.5 pl-9 pr-3 rounded-none focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary placeholder:text-outline transition-all"
                placeholder="Search targets (CMD+K)…"
              />
            </div>
            {selected.size > 0 ? (
              <button
                onClick={() => setDeleteOpen(true)}
                className="border border-error text-error hover:bg-error/10 font-data-mono-bold text-data-mono-bold px-4 py-2 flex items-center gap-2 transition-colors shrink-0"
              >
                <Icon name="delete" className="text-[18px]" />
                DELETE SELECTED ({selected.size})
              </button>
            ) : null}
            <button
              onClick={() => setModalOpen(true)}
              className="bg-primary-container text-on-primary-container hover:bg-primary-fixed font-data-mono-bold text-data-mono-bold px-4 py-2 border border-primary-container flex items-center gap-2 transition-colors shrink-0"
            >
              <Icon name="add" className="text-[18px]" />
              NEW TARGET
            </button>
          </div>
        </div>

        <div className="bg-surface-container border border-outline-variant flex-1 flex flex-col overflow-hidden relative">
          <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-surface border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant sticky top-0 z-10">
            <div className="col-span-4 md:col-span-3 flex items-center gap-3">
              <input
                type="checkbox"
                aria-label="Select all"
                checked={selected.size === rows.length && rows.length > 0}
                onChange={(e) => setSelected(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())}
                className="bg-surface-container-low border border-outline-variant text-primary cursor-pointer"
              />
              TARGET IDENTIFIER
            </div>
            <div className="col-span-3 md:col-span-2">PLATFORM</div>
            <div className="col-span-2 hidden md:block text-right">ASSETS</div>
            <div className="col-span-3 md:col-span-2 text-right">FINDINGS (OPEN)</div>
            <div className="col-span-2 hidden lg:block text-right">LAST RECON RUN</div>
            <div className="col-span-2 col-start-11 text-right">STATUS</div>
          </div>

          <div className="flex-1 overflow-y-auto font-data-mono text-data-mono">
            {rows.map((r) => (
              <div
                key={r.id}
                className={
                  "grid grid-cols-12 gap-4 px-4 py-3 border-b border-outline-variant hover:bg-surface-container-highest cursor-pointer group transition-colors border-l-2 hover:border-l-primary items-center " +
                  (selected.has(r.id) ? "bg-surface-container-high border-l-primary" : "border-l-transparent")
                }
              >
                <div className="col-span-4 md:col-span-3 font-data-mono-bold text-on-surface group-hover:text-primary transition-colors flex items-center gap-3 truncate">
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.name}`}
                    checked={selected.has(r.id)}
                    onChange={() => toggle(r.id)}
                    className="bg-surface-container-low border border-outline-variant text-primary cursor-pointer shrink-0"
                  />
                  <Icon name={r.icon} className="text-outline text-[16px]" />
                  {r.name}
                </div>
                <div className="col-span-3 md:col-span-2 flex items-center">
                  <span className="px-2 py-0.5 bg-level-2 text-on-surface border border-outline-variant rounded-sm text-[11px]">{r.platform}</span>
                </div>
                <div className="col-span-2 hidden md:block text-right text-on-surface-variant">{r.assets}</div>
                <div className="col-span-3 md:col-span-2 flex items-center justify-end gap-2">
                  <span className="text-error font-data-mono-bold">{r.open}</span>
                  <span className="text-secondary font-data-mono-bold">{r.triaged}</span>
                </div>
                <div className="col-span-2 hidden lg:block text-right text-on-surface-variant text-[11px]">{r.last}</div>
                <div className="col-span-2 col-start-11 text-right flex justify-end">
                  {r.status === "Active" ? (
                    <span className="px-2 py-0.5 bg-primary-container/10 text-primary border border-primary/30 rounded-sm text-[11px] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary inline-block" /> Active
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 bg-surface-container-highest text-on-surface-variant border border-outline-variant rounded-sm text-[11px] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-outline-variant inline-block" /> Paused
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {modalOpen ? <AddTargetModal onClose={() => setModalOpen(false)} /> : null}
      {deleteOpen ? (
        <PurgeModal
          names={rows.filter((r) => selected.has(r.id)).map((r) => r.name)}
          onCancel={() => setDeleteOpen(false)}
          onConfirm={purge}
        />
      ) : null}
      {toast ? (
        <div className="fixed top-panel_padding right-panel_padding z-[60] border border-[#4ade80] text-[#4ade80] bg-[#4ade80]/10 px-4 py-3 flex items-start gap-3 shadow-[0_0_15px_rgba(74,222,128,0.2)] rounded">
          <Icon name="check_circle" className="text-[20px] mt-0.5" />
          <div className="flex flex-col gap-1">
            <span className="font-data-mono-bold text-[14px] uppercase tracking-wider">Forensic wipe complete</span>
            <span className="font-data-mono text-[12px] opacity-80">{toast}</span>
          </div>
        </div>
      ) : null}
    </>
  );
}

function PurgeModal({ names, onCancel, onConfirm }: { names: string[]; onCancel: () => void; onConfirm: () => void }) {
  const [text, setText] = useState("");
  const armed = text === "PURGE";
  const dialogRef = useFocusTrap<HTMLDivElement>(onCancel);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-surface-container-lowest/90 backdrop-blur-sm" onClick={onCancel} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Confirm permanent deletion"
        tabIndex={-1}
        className="relative bg-surface-container-lowest border border-outline-variant w-full max-w-[450px] mx-4 shadow-[0_0_40px_rgba(147,0,10,0.3)] flex flex-col outline-none"
      >
        <div className="px-6 py-4 border-b border-outline-variant bg-surface-container-low">
          <h3 className="font-display-id text-[14px] tracking-widest text-error uppercase">Confirm permanent deletion</h3>
        </div>
        <div className="p-6 flex flex-col gap-4">
          <p className="font-body-sm text-on-surface-variant leading-relaxed">
            This is irreversible and purges all telemetry, artifacts, and findings for the following targets:
          </p>
          <div className="bg-surface-container-high border border-outline-variant p-3 max-h-32 overflow-y-auto">
            <ul className="font-data-mono text-[12px] text-primary flex flex-col gap-1">
              {names.map((n) => (<li key={n}>&gt; {n}</li>))}
            </ul>
          </div>
          <label className="flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant">Type &quot;PURGE&quot; to authorize forensic wipe</span>
            <input
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full bg-surface-container-lowest border border-outline-variant text-error font-data-mono text-data-mono px-3 py-2 focus:outline-none focus:border-error focus:ring-1 focus:ring-error placeholder:text-outline/30 transition-all"
              placeholder="PURGE"
            />
          </label>
        </div>
        <div className="px-6 py-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-4">
          <button onClick={onCancel} className="font-data-mono text-[12px] text-on-surface-variant hover:text-on-surface transition-colors">[ CANCEL ]</button>
          <button
            onClick={onConfirm}
            disabled={!armed}
            className="bg-error text-on-error px-4 py-2 font-data-mono-bold text-[12px] hover:bg-error/90 transition-colors shadow-[0_0_15px_rgba(147,0,10,0.4)] disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
          >
            [ AUTHORIZE PURGE ]
          </button>
        </div>
      </div>
    </div>
  );
}

function AddTargetModal({ onClose }: { onClose: () => void }) {
  const [rules, setRules] = useState<{ pattern: string; effect: "allow" | "deny" }[]>([
    { pattern: "*.sandbox-alpha.test", effect: "allow" },
    { pattern: "staging.sandbox-alpha.test", effect: "deny" },
  ]);
  const dialogRef = useFocusTrap<HTMLDivElement>(onClose);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Define new target"
        tabIndex={-1}
        className="relative bg-surface border border-outline-variant w-full max-w-2xl mx-4 shadow-[0_8px_32px_rgba(0,0,0,0.8)] flex flex-col max-h-[90vh] outline-none"
      >
        <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center bg-surface-container-low">
          <h3 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
            <Icon name="add_box" className="text-primary" />Define New Target
          </h3>
          <button onClick={onClose} aria-label="Close" className="text-on-surface-variant hover:text-on-surface p-1">
            <Icon name="close" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 flex flex-col gap-6 font-data-mono text-data-mono">
          <div className="p-3 bg-surface-container-highest border-l-2 border-secondary text-on-surface-variant text-[12px] flex items-start gap-3">
            <Icon name="warning" className="text-secondary text-[16px] mt-0.5" />
            <p>
              <strong>IMMUTABLE SCOPE:</strong> Scope rules cannot be modified once committed. Every rule is written
              transactionally and audited. Deny-by-default is enforced in the gateway.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Target Name</span>
              <input className="w-full bg-surface-container-low border border-outline-variant text-on-surface px-3 py-2 focus:outline-none focus:border-primary transition-all" placeholder="e.g., Sandbox Alpha" />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Platform / Source</span>
              <select className="w-full bg-surface-container-low border border-outline-variant text-on-surface px-3 py-2 appearance-none focus:outline-none focus:border-primary">
                <option>Bug Bounty Program (BBS)</option>
                <option>HackerOne</option>
                <option>Bugcrowd</option>
                <option>Internal Red Team</option>
              </select>
            </label>
          </div>

          <div className="border-t border-outline-variant pt-4 mt-2">
            <div className="flex justify-between items-center mb-4">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Scope Rules Configuration</span>
              <button
                onClick={() => setRules((r) => [...r, { pattern: "", effect: "allow" }])}
                className="text-primary hover:text-primary-fixed text-[12px] flex items-center gap-1"
              >
                <Icon name="add" className="text-[14px]" /> Add Rule
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {rules.map((rule, i) => (
                <div key={i} className="flex items-center gap-2 bg-surface-container border border-outline-variant p-2">
                  <div className="flex-1 flex items-center gap-2">
                    <Icon name="regular_expression" className="text-outline text-[16px]" />
                    <input
                      className="w-full bg-transparent border-none text-on-surface p-0 focus:ring-0 text-[13px] font-data-mono"
                      value={rule.pattern}
                      onChange={(e) => setRules((rs) => rs.map((x, j) => (j === i ? { ...x, pattern: e.target.value } : x)))}
                    />
                  </div>
                  <div className="flex items-center gap-1 border border-outline-variant bg-surface rounded-sm p-0.5">
                    {(["allow", "deny"] as const).map((eff) => (
                      <button
                        key={eff}
                        onClick={() => setRules((rs) => rs.map((x, j) => (j === i ? { ...x, effect: eff } : x)))}
                        className={
                          "px-2 py-0.5 text-[11px] font-bold uppercase " +
                          (rule.effect === eff
                            ? eff === "allow"
                              ? "bg-[#004e5a] text-[#8aebff] border border-[#005763]"
                              : "bg-[#690005] text-[#ffb4ab] border border-[#93000a]"
                            : "text-on-surface-variant hover:text-on-surface")
                        }
                      >
                        {eff}
                      </button>
                    ))}
                  </div>
                  <button onClick={() => setRules((rs) => rs.filter((_, j) => j !== i))} aria-label="Remove rule" className="text-on-surface-variant hover:text-error p-1 ml-1">
                    <Icon name="delete" className="text-[16px]" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-on-surface-variant hover:text-on-surface font-data-mono-bold border border-transparent hover:border-outline-variant transition-colors">CANCEL</button>
          <button onClick={onClose} className="px-4 py-2 bg-primary-container text-on-primary-container hover:bg-primary-fixed font-data-mono-bold border border-primary-container flex items-center gap-2 transition-colors">
            <Icon name="save" className="text-[18px]" /> COMMIT TARGET
          </button>
        </div>
      </div>
    </div>
  );
}
