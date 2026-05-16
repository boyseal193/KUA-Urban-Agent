"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  rightSlot,
  className,
}: PageHeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between border-b border-border/60 pb-5",
        className
      )}
    >
      <div className="space-y-1.5">
        {eyebrow && (
          <p className="tactical-mono">{eyebrow}</p>
        )}
        <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {title}
        </h1>
        {subtitle && (
          <p className="max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {rightSlot && (
        <div className="flex shrink-0 items-center gap-2">{rightSlot}</div>
      )}
    </motion.header>
  );
}
