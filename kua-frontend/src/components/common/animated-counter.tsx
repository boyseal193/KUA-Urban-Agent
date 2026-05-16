"use client";

import * as React from "react";
import {
  animate,
  useInView,
  useMotionValue,
  useTransform,
  motion,
} from "framer-motion";
import { cn } from "@/lib/utils";

interface AnimatedCounterProps {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
  prefix?: string;
  suffix?: string;
  decimals?: number;
}

const defaultFmt = (n: number, decimals = 0) =>
  n.toLocaleString("en-EU", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

export function AnimatedCounter({
  value,
  format,
  duration = 1.4,
  className,
  prefix = "",
  suffix = "",
  decimals = 0,
}: AnimatedCounterProps) {
  const ref = React.useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const mv = useMotionValue(0);
  const display = useTransform(mv, (latest) =>
    format ? format(latest) : defaultFmt(latest, decimals)
  );

  React.useEffect(() => {
    if (!inView) return;
    const controls = animate(mv, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
    });
    return () => controls.stop();
  }, [inView, value, duration, mv]);

  return (
    <span ref={ref} className={cn("tabular-nums", className)}>
      {prefix}
      <motion.span>{display}</motion.span>
      {suffix}
    </span>
  );
}
