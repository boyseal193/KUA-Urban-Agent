"use client";

import * as React from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

type GlassCardProps = Omit<HTMLMotionProps<"div">, "children"> & {
  glow?: "none" | "cyan" | "neon" | "rose";
  corners?: boolean;
  scanline?: boolean;
  children?: React.ReactNode;
};

export function GlassCard({
  className,
  glow = "none",
  corners = false,
  scanline = false,
  children,
  ...props
}: GlassCardProps) {
  const glowClass =
    glow === "cyan"
      ? "shadow-glow"
      : glow === "neon"
      ? "shadow-glow-neon"
      : glow === "rose"
      ? "shadow-glow-rose"
      : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-5% 0px" }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "relative rounded-xl border border-border/60 bg-card/70 backdrop-blur-xl shadow-panel overflow-hidden",
        glowClass,
        scanline && "scan-overlay",
        className
      )}
      {...props}
    >
      {corners && <CornerMarks />}
      {children}
    </motion.div>
  );
}

function CornerMarks() {
  const lines =
    "absolute h-3 w-3 border-primary/60 pointer-events-none";
  return (
    <>
      <span className={cn(lines, "top-1 left-1 border-t border-l")} />
      <span className={cn(lines, "top-1 right-1 border-t border-r")} />
      <span className={cn(lines, "bottom-1 left-1 border-b border-l")} />
      <span className={cn(lines, "bottom-1 right-1 border-b border-r")} />
    </>
  );
}
