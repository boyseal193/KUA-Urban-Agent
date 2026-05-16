"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PropertyRecord } from "@/lib/api/types";

interface DistrictBarChartProps {
  deals: PropertyRecord[];
}

export function DistrictBarChart({ deals }: DistrictBarChartProps) {
  const buckets: Record<string, { count: number; sumScore: number }> = {};
  for (const d of deals) {
    const k = (d.neighbourhood || "Unknown").trim() || "Unknown";
    buckets[k] ??= { count: 0, sumScore: 0 };
    buckets[k].count++;
    buckets[k].sumScore += Number(d.score) || 0;
  }
  const data = Object.entries(buckets)
    .map(([district, v]) => ({
      district,
      count: v.count,
      avgScore: v.count ? Math.round(v.sumScore / v.count) : 0,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <BarChart
          data={data}
          margin={{ top: 8, right: 8, left: -10, bottom: 0 }}
        >
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="district"
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
            cursor={{ fill: "rgba(56,225,255,0.05)" }}
            contentStyle={{
              background: "rgba(10,13,18,0.95)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 8,
              fontSize: 11,
              fontFamily: "var(--font-mono)",
            }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((d) => (
              <Cell
                key={d.district}
                fill={
                  d.avgScore >= 80
                    ? "#7CFAB3"
                    : d.avgScore >= 65
                    ? "#38E1FF"
                    : d.avgScore >= 55
                    ? "#F5B400"
                    : "#FF4D6D"
                }
                fillOpacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
