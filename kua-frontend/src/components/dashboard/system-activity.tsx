"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Activity } from "lucide-react";

import { cn } from "@/lib/utils";

interface ActivityItem {
  label: string;
  value: string;
  status: "ok" | "warn" | "err";
}

const items: ActivityItem[] = [
  { label: "FastAPI · /scan", value: "200ms · OK", status: "ok" },
  { label: "Supabase · properties", value: "synced", status: "ok" },
  { label: "OpenAI · gpt-5", value: "1.2s · OK", status: "ok" },
  { label: "Idealista scraper", value: "throttled", status: "warn" },
  { label: "Excel exporter", value: "ready", status: "ok" },
  { label: "Geo-coder", value: "200ms · OK", status: "ok" },
];

const STATUS = {
  ok: "#7CFAB3",
  warn: "#F5B400",
  err: "#FF4D6D",
};

export function SystemActivity({ className }: { className?: string }) {
  const [pulse, setPulse] = React.useState(0);

  React.useEffect(() => {
    const id = setInterval(() => setPulse((p) => p + 1), 1800);
    return () => clearInterval(id);
  }, []);

  return (
    <div className={cn("panel relative overflow-hidden p-5", className)}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            System Activity
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
          ALL SYSTEMS OPERATIONAL
        </span>
      </div>

      <div className="space-y-1.5">
        {items.map((item, i) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="flex items-center justify-between rounded border border-border/40 bg-white/[0.02] px-2.5 py-1.5"
          >
            <div className="flex items-center gap-2">
              <span
                className="badge-dot"
                style={{
                  backgroundColor: STATUS[item.status],
                  boxShadow: `0 0 6px ${STATUS[item.status]}`,
                }}
              />
              <span className="text-xs text-foreground/80">{item.label}</span>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {item.value}
            </span>
          </motion.div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>heartbeat #{pulse}</span>
        <span className="text-accent">stream live</span>
      </div>
    </div>
  );
}
