"use client";

/**
 * Animation primitives for the auth surface, on MNEMOS tokens.
 *
 * These are rebuilt rather than dropped in from the shadcn source they were
 * modelled on. Three reasons, all from CLAUDE.md §8:
 *
 *   - Icons are lucide SVGs through the central Icon component. The original
 *     pulled PNGs from cdn1.iconfinder.com and cdn.jsdelivr.net on every render.
 *   - The console must stay PWA-offline-safe. No remote asset is fetched here.
 *   - Colours come from the dark Material-3 token set (cyan primary, amber
 *     secondary), not a hardcoded #3b82f6 on a light background.
 *
 * Every animation respects prefers-reduced-motion.
 */

import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useReducedMotion,
} from "motion/react";
import {
  forwardRef,
  memo,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

/* ------------------------------------------------------------------ *
 * RevealInput — a field that lights up under the cursor
 * ------------------------------------------------------------------ */
export const RevealInput = memo(
  forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
    function RevealInput({ className = "", type, ...props }, ref) {
      const mouseX = useMotionValue(0);
      const mouseY = useMotionValue(0);
      const reduced = useReducedMotion();

      // The gradient follows the pointer. Tracked as motion values rather than
      // React state so it never triggers a re-render while moving.
      const background = useMotionTemplate`radial-gradient(120px circle at ${mouseX}px ${mouseY}px, rgba(138, 235, 255, 0.55), transparent 80%)`;

      return (
        <motion.div
          style={reduced ? undefined : { background }}
          onMouseMove={(e) => {
            const { left, top } = e.currentTarget.getBoundingClientRect();
            mouseX.set(e.clientX - left);
            mouseY.set(e.clientY - top);
          }}
          className="group/input rounded p-px transition duration-300 bg-level-2"
        >
          <input
            ref={ref}
            type={type}
            className={
              "flex h-10 w-full rounded border-none bg-level-0 px-3 py-2 " +
              "font-data-mono text-data-mono text-on-surface " +
              "placeholder:text-outline transition duration-300 " +
              "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary " +
              "disabled:cursor-not-allowed disabled:opacity-50 " +
              className
            }
            {...props}
          />
        </motion.div>
      );
    },
  ),
);

/* ------------------------------------------------------------------ *
 * BoxReveal — a wipe that uncovers its children once, on entry
 * ------------------------------------------------------------------ */
export const BoxReveal = memo(function BoxReveal({
  children,
  delay = 0,
  className = "",
  width = "fit-content",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  width?: string;
}) {
  // No covering overlay. This deliberately does less than the component it was
  // modelled on, and the reason is worth recording.
  //
  // Three attempts drove a wipe across the content: useAnimation + useInView,
  // then motion's initial/animate, then a CSS keyframe. Each one left the block
  // parked on top of the sign-in fields when the animation did not start — and a
  // login form nobody can see is a far worse outcome than a login form that does
  // not shimmer. The failure mode is asymmetric, so the safe design is one where
  // nothing is ever painted over the content in the first place.
  //
  // The entrance is a fade-and-rise on the content itself. If animations never
  // run, the content is simply there, which is the correct degraded state.
  return (
    <div style={{ width }} className={className}>
      <div
        className="motion-safe:animate-fade-up"
        style={{ animationDelay: `${delay + 0.12}s` }}
      >
        {children}
      </div>
    </div>
  );
});

/* ------------------------------------------------------------------ *
 * OrbitRing — concentric rings of orbiting nodes
 *
 * Purely decorative, so it is aria-hidden and disabled entirely under
 * prefers-reduced-motion rather than merely slowed.
 * ------------------------------------------------------------------ */
export const OrbitRing = memo(function OrbitRing({
  radius,
  duration = 24,
  delay = 0,
  reverse = false,
  children,
}: {
  radius: number;
  duration?: number;
  delay?: number;
  reverse?: boolean;
  children: ReactNode;
}) {
  const reduced = useReducedMotion();

  return (
    <>
      <svg
        aria-hidden
        className="pointer-events-none absolute inset-0 size-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle
          cx="50%"
          cy="50%"
          r={radius}
          fill="none"
          className="stroke-level-2"
          strokeWidth={1}
          strokeDasharray="2 6"
        />
      </svg>
      <div
        aria-hidden
        style={
          {
            "--duration": duration,
            "--radius": radius,
            "--delay": -delay,
          } as React.CSSProperties
        }
        className={
          "absolute flex size-full transform-gpu items-center justify-center rounded-full " +
          (reduced
            ? ""
            : "animate-orbit [animation-delay:calc(var(--delay)*1000ms)] ") +
          (reverse ? "[animation-direction:reverse]" : "")
        }
      >
        {children}
      </div>
    </>
  );
});
