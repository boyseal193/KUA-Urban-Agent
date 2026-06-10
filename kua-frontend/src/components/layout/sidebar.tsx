"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  BadgeCheck,
  BrainCircuit,
  Columns3,
  Download,
  History,
  LayoutGrid,
  MapPinned,
  Radar,
  Settings,
  ShieldCheck,
  Sliders,
  Wrench,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { APP_NAME, APP_SHORT } from "@/lib/constants";
import { VerticalSwitcher } from "@/components/layout/vertical-switcher";
import { VERTICAL_META, verticalFromPathname } from "@/lib/vertical";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  kbd?: string;
};

const STORAGE_NAV: NavItem[] = [
  { href: "/dashboard", label: "Command", icon: LayoutGrid, kbd: "1" },
  { href: "/pipeline", label: "Pipeline", icon: Columns3, kbd: "2" },
  { href: "/scan", label: "Live Scan", icon: Radar, kbd: "3" },
  { href: "/scans", label: "History", icon: History, kbd: "4" },
  { href: "/map", label: "Tactical Map", icon: MapPinned, kbd: "5" },
  { href: "/intelligence", label: "Intelligence", icon: BrainCircuit, kbd: "6" },
  { href: "/admin", label: "Admin", icon: Wrench, kbd: "7" },
];

const LAUNDRY_NAV: NavItem[] = [
  { href: "/laundry/dashboard", label: "Dashboard", icon: LayoutGrid, kbd: "1" },
  { href: "/laundry/pipeline", label: "Pipeline", icon: Columns3, kbd: "2" },
  { href: "/laundry/manual-review", label: "Manual Review", icon: Activity, kbd: "3" },
  { href: "/laundry/approved", label: "Approved", icon: BadgeCheck, kbd: "4" },
  { href: "/laundry/rejected", label: "Rejected", icon: XCircle, kbd: "5" },
  { href: "/laundry/map", label: "Map", icon: MapPinned, kbd: "6" },
  { href: "/laundry/scans", label: "Scans", icon: Radar, kbd: "7" },
  { href: "/laundry/exports", label: "Exports", icon: Download, kbd: "8" },
  { href: "/laundry/settings", label: "Settings", icon: Sliders, kbd: "9" },
];

function Logo() {
  return (
    <div className="relative flex h-9 w-9 items-center justify-center rounded-md border border-primary/40 bg-primary/10 shadow-glow">
      <span className="font-display text-base font-bold text-primary">K</span>
      <span className="absolute -inset-px rounded-md opacity-50 animate-pulse-glow" />
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "accent" | "rose";
}) {
  const color =
    tone === "accent"
      ? "text-accent"
      : tone === "rose"
      ? "text-destructive"
      : "text-foreground/80";
  return (
    <div className="flex items-center justify-between py-0.5 font-mono text-[10px] uppercase tracking-widest">
      <span className="text-muted-foreground">{label}</span>
      <span className={color}>{value}</span>
    </div>
  );
}

interface SidebarShellProps {
  className?: string;
  layoutId?: string;
}

function SidebarShell({ className, layoutId = "active-nav-pill" }: SidebarShellProps) {
  const pathname = usePathname();
  const vertical = verticalFromPathname(pathname);
  const meta = VERTICAL_META[vertical];
  const items = vertical === "laundry" ? LAUNDRY_NAV : STORAGE_NAV;
  const sectionLabel =
    vertical === "laundry" ? "Laundry Intelligence" : "Storage Operations";

  return (
    <div
      className={cn(
        "flex h-full w-full flex-col border-r border-border/60 bg-card/40 backdrop-blur-xl",
        className
      )}
    >
      <div className="flex h-16 items-center gap-3 border-b border-border/60 px-5">
        <Logo />
        <div className="leading-tight">
          <div className="font-display text-[15px] font-semibold tracking-tight text-foreground">
            {APP_SHORT}
          </div>
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
            {APP_NAME}
          </div>
        </div>
      </div>

      <div className="border-b border-border/60 px-3 py-3">
        <VerticalSwitcher className="w-full justify-center" />
        <div className="mt-2 flex items-center justify-between px-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
          <span>Vertical</span>
          <span style={{ color: meta.accent }}>{meta.short}</span>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-3">
        <div className="px-2 pb-2 pt-1 tactical-mono">{sectionLabel}</div>
        {items.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/[0.08] text-foreground"
                  : "text-muted-foreground hover:bg-white/[0.03] hover:text-foreground"
              )}
            >
              {active && (
                <motion.span
                  layoutId={layoutId}
                  className="absolute inset-y-1 left-0 w-[2px] rounded-r shadow-glow"
                  style={{ background: meta.accent }}
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <span
                className={cn(
                  "shrink-0 transition-colors",
                  active ? "text-foreground" : "text-muted-foreground"
                )}
                style={active ? { color: meta.accent } : undefined}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="flex-1">{item.label}</span>
              {item.kbd && (
                <kbd className="hidden rounded border border-border/60 bg-white/[0.04] px-1.5 py-px font-mono text-[9px] text-muted-foreground group-hover:inline-block">
                  ⌘{item.kbd}
                </kbd>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border/60 p-3">
        <div className="rounded-lg border border-border/60 bg-card/60 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="tactical-mono">System</span>
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-accent">
              <span className="badge-dot animate-pulse bg-accent shadow-glow-neon" />
              ONLINE
            </span>
          </div>
          <Metric label="Latency" value="42ms" />
          <Metric label="Backend" value="OK" tone="accent" />
          <Metric label="Auth" value="JWT" />
        </div>

        <div className="mt-2 flex items-center gap-2 px-2 text-[10px] text-muted-foreground/70">
          <ShieldCheck className="h-3 w-3" />
          <span className="font-mono uppercase tracking-widest">Tier-1</span>
          <span className="ml-auto inline-flex items-center gap-1">
            <Settings className="h-3 w-3" />
          </span>
        </div>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden h-screen w-[244px] shrink-0 lg:block">
      <SidebarShell />
    </aside>
  );
}

export function MobileSidebar() {
  return <SidebarShell layoutId="active-nav-pill-mobile" />;
}
