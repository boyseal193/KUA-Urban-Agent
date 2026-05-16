"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PropertyRecord } from "@/lib/api/types";

interface ScoreDistributionChartProps {
  deals: PropertyRecord[];
}

export function ScoreDistributionChart({ deals }: ScoreDistributionChartProps) {
  const bins = Array.from({ length: 10 }, (_, i) => ({
    bin: `${i * 10}-${i * 10 + 9}`,
    count: 0,
  }));
  for (const d of deals) {
    const s = Number(d.score);
    if (!Number.isFinite(s)) continue;
    const idx = Math.min(9, Math.max(0, Math.floor(s / 10)));
    bins[idx].count++;
  }

  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <AreaChart data={bins} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="scoregrad" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#38E1FF" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#38E1FF" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="bin"
            stroke="#7C8699"
            tick={{ fontSize: 10, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
          />
          <YAxis
            stroke="#7C8699"
            tick={{ fontSize: 10, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              background: "rgba(10,13,18,0.95)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 8,
              fontSize: 11,
              fontFamily: "var(--font-mono)",
            }}
            labelStyle={{ color: "#7C8699", textTransform: "uppercase" }}
            itemStyle={{ color: "#38E1FF" }}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="#38E1FF"
            strokeWidth={2}
            fill="url(#scoregrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
