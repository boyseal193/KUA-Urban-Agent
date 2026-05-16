"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface StatusPillProps {
  label: string;
  color?: string;
  pulse?: boolean;
  className?: string;
}

export function StatusPill({
  label,
  color = "#7CFAB3",
  pulse = true,
  className,
}: StatusPillProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 backdrop-blur",
        className
      )}
    >
      <span className="relative inline-flex h-1.5 w-1.5">
        {pulse && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ backgroundColor: color }}
            animate={{ scale: [1, 2.2, 1], opacity: [0.65, 0, 0.65] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <span
          className="relative inline-block h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}
        />
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-foreground/80">
        {label}
      </span>
    </div>
  );
}
