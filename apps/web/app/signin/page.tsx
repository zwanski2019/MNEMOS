"use client";

import { useState, type FormEvent } from "react";
import { Icon } from "@/components/Icon";
import {
  BoxReveal,
  OrbitRing,
  RevealInput,
} from "@/components/ui/motion-primitives";

/**
 * Sign in / sign up.
 *
 * Nothing on this page gates the console. Reading memory is open to everyone,
 * forever — an account exists only to *act*: create targets, launch scans, edit
 * scope. Those spend real money and touch someone else's infrastructure, which is
 * where the boundary belongs.
 */

const GATEWAY =
  process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8080";

// Orbiting nodes are local lucide glyphs. The design this was modelled on fetched
// PNGs from a CDN on every render; the console has to work offline.
const ORBITS: { radius: number; duration: number; delay: number; reverse?: boolean; icon: string }[] = [
  { radius: 90, duration: 22, delay: 0, icon: "database" },
  { radius: 90, duration: 22, delay: 11, icon: "memory" },
  { radius: 150, duration: 30, delay: 0, reverse: true, icon: "search_check" },
  { radius: 150, duration: 30, delay: 10, reverse: true, icon: "security" },
  { radius: 150, duration: 30, delay: 20, reverse: true, icon: "history" },
  { radius: 215, duration: 40, delay: 0, icon: "cloud" },
  { radius: 215, duration: 40, delay: 20, icon: "smart_toy" },
];

export default function SignInPage() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setOk("");

    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("That does not look like an email address.");
      return;
    }
    if (mode === "signup" && password.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(`${GATEWAY}/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? "Sign in failed.");
        return;
      }
      // The token authorises write calls. Reads never need it.
      sessionStorage.setItem("mnemos_token", body.token);
      setOk(
        mode === "signup"
          ? `Account created — ${body.trial_days_left} days of full access.`
          : "Signed in.",
      );
    } catch {
      setError(
        `Could not reach the gateway at ${GATEWAY}. The console still works — reading memory never needs an account.`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Decorative half */}
      <section className="hidden lg:flex w-1/2 relative items-center justify-center bg-level-0 border-r border-level-2">
        <div className="relative size-[520px] flex items-center justify-center">
          {ORBITS.map((o, i) => (
            <OrbitRing
              key={i}
              radius={o.radius}
              duration={o.duration}
              delay={o.delay}
              reverse={o.reverse}
            >
              <span className="size-8 rounded-full bg-level-1 border border-level-2 flex items-center justify-center">
                <Icon name={o.icon} className="text-primary text-sm" />
              </span>
            </OrbitRing>
          ))}
          <div className="text-center px-8 z-10">
            <h1 className="font-display-id text-display-id tracking-tighter text-primary">
              MNEMOS
            </h1>
            <p className="font-data-mono text-data-mono text-on-surface-variant mt-3 max-w-xs mx-auto">
              An autonomous recon agent whose memory is the product.
            </p>
          </div>
        </div>
        <p className="absolute bottom-6 left-0 right-0 text-center font-data-mono text-[10px] text-outline">
          Reading memory is free forever. An account is only needed to act on it.
        </p>
      </section>

      {/* Form half */}
      <section className="w-full lg:w-1/2 flex flex-col justify-center items-center px-8 py-12 overflow-y-auto">
        <div className="w-full max-w-sm flex flex-col gap-4">
          <BoxReveal>
            <h2 className="font-headline-md text-headline-md text-on-surface text-2xl">
              {mode === "login" ? "Sign in" : "Start your trial"}
            </h2>
          </BoxReveal>

          <BoxReveal width="100%">
            <p className="font-data-mono text-data-mono text-on-surface-variant">
              {mode === "login"
                ? "Sign in to create targets and launch scans."
                : "Five days of full access. No card required to start."}
            </p>
          </BoxReveal>

          <form onSubmit={submit} className="flex flex-col gap-4 mt-2">
            <BoxReveal width="100%" className="flex flex-col gap-2">
              <label
                htmlFor="email"
                className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest"
              >
                Email
              </label>
              <RevealInput
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </BoxReveal>

            <BoxReveal width="100%" className="flex flex-col gap-2">
              <label
                htmlFor="password"
                className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest"
              >
                Password
              </label>
              <div className="relative">
                <RevealInput
                  id="password"
                  type={visible ? "text" : "password"}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  placeholder={
                    mode === "signup" ? "at least 10 characters" : "••••••••••"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setVisible((v) => !v)}
                  aria-label={visible ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-on-surface-variant hover:text-primary transition-colors"
                >
                  <Icon name={visible ? "search" : "security"} className="text-sm" />
                </button>
              </div>
            </BoxReveal>

            {error && (
              <p
                role="alert"
                className="font-data-mono text-data-mono text-error border-l-2 border-error pl-3"
              >
                {error}
              </p>
            )}
            {ok && (
              <p
                role="status"
                className="font-data-mono text-data-mono text-primary border-l-2 border-primary pl-3"
              >
                {ok}
              </p>
            )}

            <BoxReveal width="100%">
              <button
                type="submit"
                disabled={busy}
                className="w-full h-10 rounded bg-primary-container text-level-0 font-data-mono-bold
                  hover:opacity-90 transition-opacity disabled:opacity-50
                  disabled:cursor-not-allowed focus-visible:outline-none
                  focus-visible:ring-2 focus-visible:ring-primary"
              >
                {busy
                  ? "…"
                  : mode === "login"
                    ? "Sign in →"
                    : "Start 5-day trial →"}
              </button>
            </BoxReveal>
          </form>

          <button
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError("");
              setOk("");
            }}
            className="font-data-mono text-data-mono text-primary hover:underline mt-2 text-center"
          >
            {mode === "login"
              ? "No account? Start a free trial"
              : "Already have an account? Sign in"}
          </button>

          <div className="mt-6 pt-4 border-t border-level-2 font-data-mono text-[10px] text-outline space-y-1">
            <p>
              Passwords are hashed with scrypt and a per-user salt. Sessions store
              only a hash of the token — a dump of the table does not let anyone
              log in.
            </p>
            <p>
              Checkout, when a trial ends, happens on the billing provider&apos;s
              domain. No card details are handled by MNEMOS.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
