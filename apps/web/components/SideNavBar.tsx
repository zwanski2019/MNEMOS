"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/Icon";

type NavItem = { href: string; icon: string; label: string };

const NAV: NavItem[] = [
  { href: "/", icon: "dashboard", label: "Overview" },
  { href: "/targets", icon: "target", label: "Targets" },
  { href: "/runs", icon: "play_circle", label: "Live Runs" },
  { href: "/findings", icon: "search_check", label: "Findings" },
  { href: "/memory", icon: "database", label: "Memory" },
  { href: "/scope", icon: "security", label: "Scope" },
  { href: "/audit", icon: "history", label: "Audit" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function SideNavBar() {
  const pathname = usePathname();

  return (
    <nav className="w-nav_rail_width h-screen fixed left-0 top-0 bg-surface-container-low border-r border-outline-variant flex flex-col items-center py-gutter z-40">
      <Link
        href="/"
        className="mb-8 flex flex-col items-center cursor-pointer rounded outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-container-low"
        aria-label="MNEMOS — Overview"
      >
        <Icon name="trip_origin" filled className="text-primary text-[28px]" />
      </Link>

      <div className="flex-1 w-full flex flex-col items-center gap-2">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              aria-label={item.label}
              aria-current={active ? "page" : undefined}
              className={
                "w-full flex flex-col items-center py-3 transition-all duration-150 ease-in-out group relative outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary " +
                (active
                  ? "text-primary border-l-2 border-primary bg-surface-container-high"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest")
              }
            >
              <Icon name={item.icon} filled={active} className="text-[22px]" />
              <span className="font-label-caps text-label-caps mt-1 hidden lg:block text-[9px] uppercase">
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>

      <div className="mt-auto w-full flex flex-col items-center">
        <Link
          href="/settings"
          title="Settings"
          aria-label="Settings"
          aria-current={pathname.startsWith("/settings") ? "page" : undefined}
          className="w-full flex flex-col items-center py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest transition-all duration-150 ease-in-out outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
        >
          <Icon name="settings" className="text-[22px]" />
        </Link>
      </div>
    </nav>
  );
}
