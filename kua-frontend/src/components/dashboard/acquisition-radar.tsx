"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Radar as RadarIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RadarPoint {
  id: string;
  angle: number;   // 0..360
  radius: number;  // 0..1
  label?: string;
  tone?: "core" | "review" | "reject";
}

interface AcquisitionRadarProps {
  points?: RadarPoint[];
  scanned?: number;
  className?: string;
}

const TONE_COLOR: Record<NonNullable<RadarPoint["tone"]>, string> = {
  core: "#7CFAB3",
  review: "#38E1FF",
  reject: "#FF4D6D",
};

export function AcquisitionRadar({
  points = [],
  scanned = 0,
  className,
}: AcquisitionRadarProps) {
  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <div className={cn("panel relative overflow-hidden p-5", className)}>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RadarIcon className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Acquisition Radar
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {scanned} scanned · live
        </span>
      </div>

      <div className="relative mx-auto aspect-square w-full max-w-[260px]">
        {/* rings */}
        {rings.map((r) => (
          <div
            key={r}
            className="absolute rounded-full border border-primary/15"
            style={{
              inset: `${(1 - r) * 50}%`,
            }}
          />
        ))}

        {/* cross */}
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-primary/15" />
        <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-primary/15" />

        {/* sweep */}
        <motion.div
          className="absolute inset-0 origin-center rounded-full"
          style={{
            background:
              "conic-gradient(from 0deg, transparent 0deg, rgba(56,225,255,0.35) 35deg, transparent 70deg)",
            maskImage:
              "radial-gradient(circle at center, black 60%, transparent 100%)",
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        />

        {/* core glow */}
        <div className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary shadow-glow animate-pulse-glow" />

        {/* points */}
        {points.map((p, i) => {
          const rad = (p.angle * Math.PI) / 180;
          const x = 50 + Math.cos(rad) * p.radius * 45;
          const y = 50 + Math.sin(rad) * p.radius * 45;
          const color = TONE_COLOR[p.tone ?? "review"];
          return (
            <motion.span
              key={p.id}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: i * 0.05 }}
              className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                backgroundColor: color,
                boxShadow: `0 0 8px ${color}`,
              }}
            />
          );
        })}
      </div>

      <div className="mt-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-widest">
        <Legend color={TONE_COLOR.core} label="Core" />
        <Legend color={TONE_COLOR.review} label="Review" />
        <Legend color={TONE_COLOR.reject} label="Reject" />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      <span
        className="badge-dot"
        style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
      />
      {label}
    </span>
  );
}
