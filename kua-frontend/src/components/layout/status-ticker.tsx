"use client";

import * as React from "react";
import { Activity, Cpu, Database, Globe2, Radio, Satellite } from "lucide-react";

const TICKERS = [
  { icon: Satellite, label: "MARKET PULSE", value: "Barcelona / B30 corridor" },
  { icon: Globe2, label: "FX", value: "EUR/USD 1.0782 ▴" },
  { icon: Activity, label: "EURIBOR 12M", value: "2.412% ▾" },
  { icon: Database, label: "DEAL CACHE", value: "synchronised" },
  { icon: Radio, label: "STREAM", value: "idealista / locales" },
  { icon: Cpu, label: "AI ENGINE", value: "gpt-5 / underwriting v3" },
];

export function StatusTicker() {
  return (
    <div className="border-b border-border/40 bg-card/30 backdrop-blur-xl">
      <div className="relative overflow-hidden">
        <div className="flex animate-marquee whitespace-nowrap py-1.5">
          {[...TICKERS, ...TICKERS].map((t, i) => {
            const Icon = t.icon;
            return (
              <div
                key={i}
                className="mr-10 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/80"
              >
                <Icon className="h-3 w-3 text-primary/70" />
                <span className="text-foreground/70">{t.label}</span>
                <span className="text-muted-foreground/50">/</span>
                <span className="text-accent/80">{t.value}</span>
              </div>
            );
          })}
        </div>
        <div className="pointer-events-none absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-background to-transparent" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-background to-transparent" />
      </div>
    </div>
  );
}
