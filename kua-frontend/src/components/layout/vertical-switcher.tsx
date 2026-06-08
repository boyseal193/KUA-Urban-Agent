"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { Boxes, WashingMachine } from "lucide-react";
import { motion } from "framer-motion";

import { cn } from "@/lib/utils";
import { VERTICAL_META, verticalFromPathname, type Vertical } from "@/lib/vertical";

const ITEMS: Array<{ id: Vertical; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "storage", label: VERTICAL_META.storage.label, icon: Boxes },
  { id: "laundry", label: VERTICAL_META.laundry.label, icon: WashingMachine },
];

interface VerticalSwitcherProps {
  className?: string;
  compact?: boolean;
}

/**
 * Compact two-state toggle that hands off the operator between the storage
 * vertical and the laundry vertical. The active vertical is derived from the
 * current pathname so SSR + client agree on first paint.
 */
export function VerticalSwitcher({ className, compact = false }: VerticalSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const active = verticalFromPathname(pathname);

  const go = (vertical: Vertical) => {
    if (vertical === active) return;
    router.push(VERTICAL_META[vertical].landing);
  };

  return (
    <div
      role="tablist"
      aria-label="Vertical switcher"
      className={cn(
        "relative inline-flex items-center gap-1 rounded-lg border border-border/60 bg-card/40 p-1 backdrop-blur",
        className,
      )}
    >
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = active === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => go(item.id)}
            className={cn(
              "relative z-10 inline-flex items-center gap-2 rounded-md px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest transition-colors",
              isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {isActive && (
              <motion.span
                layoutId="vertical-pill"
                transition={{ type: "spring", stiffness: 360, damping: 30 }}
                className="absolute inset-0 rounded-md bg-primary/15 ring-1 ring-primary/30"
                style={{ background: `${VERTICAL_META[item.id].accent}1A` }}
              />
            )}
            <Icon className="relative z-10 h-3.5 w-3.5" />
            {!compact && <span className="relative z-10">{item.label}</span>}
          </button>
        );
      })}
    </div>
  );
}
