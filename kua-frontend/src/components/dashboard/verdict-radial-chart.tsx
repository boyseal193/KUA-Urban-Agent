"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { PropertyRecord } from "@/lib/api/types";
import { dealStatusMeta } from "@/lib/constants";

interface VerdictRadialChartProps {
  deals: PropertyRecord[];
}

export function VerdictRadialChart({ deals }: VerdictRadialChartProps) {
  const buckets = {
    approved_candidate: 0,
    manual_review: 0,
    rejected: 0,
  } as Record<string, number>;
  for (const d of deals) {
    const s = d.deal_status || "manual_review";
    buckets[s] = (buckets[s] ?? 0) + 1;
  }

  const data = Object.entries(buckets).map(([k, v]) => ({
    name: dealStatusMeta(k).label,
    value: v,
    color: dealStatusMeta(k).color,
  }));

  const total = data.reduce((a, b) => a + b.value, 0);

  return (
    <div className="relative h-[260px] w-full">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={70}
            outerRadius={100}
            paddingAngle={3}
            stroke="none"
          >
            {data.map((d, i) => (
              <Cell key={i} fill={d.color} fillOpacity={0.85} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-display text-3xl font-semibold tabular-nums text-foreground">
          {total}
        </div>
        <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Total Deals
        </div>
      </div>
    </div>
  );
}
