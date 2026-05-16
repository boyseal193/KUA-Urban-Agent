"use client";

import { motion } from "framer-motion";
import { AlertOctagon, ShieldAlert, ShieldCheck } from "lucide-react";

interface RiskFlagsProps {
  dealKiller?: string | null;
  flags?: string[];
  className?: string;
}

export function RiskFlags({ dealKiller, flags = [], className }: RiskFlagsProps) {
  const empty = !dealKiller && flags.length === 0;
  return (
    <div className={`panel p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between border-b border-border/60 pb-3">
        <h3 className="text-sm font-semibold text-foreground">
          Risk &amp; Due Diligence
        </h3>
        <span
          className={`font-mono text-[10px] uppercase tracking-widest ${
            empty ? "text-accent" : "text-kua-amber"
          }`}
        >
          {empty ? "ALL CLEAR" : `${flags.length + (dealKiller ? 1 : 0)} ITEMS`}
        </span>
      </header>

      <div className="space-y-2">
        {dealKiller && (
          <motion.div
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/[0.08] p-3"
          >
            <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div>
              <div className="text-xs font-semibold uppercase tracking-widest text-destructive">
                DEAL KILLER
              </div>
              <p className="mt-0.5 text-sm text-foreground/90">{dealKiller}</p>
            </div>
          </motion.div>
        )}

        {flags.map((f, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.04 * (i + (dealKiller ? 1 : 0)) }}
            className="flex items-start gap-3 rounded-md border border-kua-amber/30 bg-kua-amber/[0.06] p-3"
          >
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-kua-amber" />
            <p className="text-sm text-foreground/90">{f}</p>
          </motion.div>
        ))}

        {empty && (
          <div className="flex items-center gap-3 rounded-md border border-accent/30 bg-accent/[0.06] p-3">
            <ShieldCheck className="h-4 w-4 shrink-0 text-accent" />
            <p className="text-sm text-foreground/90">
              No automatic risk flags. Manual technical &amp; legal due diligence
              still required before commitment.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
