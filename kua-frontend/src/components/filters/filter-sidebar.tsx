"use client";

import * as React from "react";
import {
  Filter as FilterIcon,
  Plus,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

import { BARCELONA_DISTRICTS, BUILDING_TYPES } from "@/lib/constants";
import { useFilters } from "@/hooks/use-filters";

export function FilterSidebar() {
  const f = useFilters();

  return (
    <aside className="panel sticky top-[120px] h-fit space-y-5 p-5">
      <Header />

      <FilterGroup label="Search">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={f.search}
            onChange={(e) => f.set("search", e.target.value)}
            placeholder="Address, ID, keyword…"
            className="pl-9 font-mono text-xs"
          />
        </div>
      </FilterGroup>

      <FilterGroup label="District">
        <Select
          value={f.district ?? "__any"}
          onValueChange={(v) => f.set("district", v === "__any" ? null : v)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Any district" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__any">Any district</SelectItem>
            {BARCELONA_DISTRICTS.map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterGroup>

      <FilterGroup
        label={`Price · €${f.priceRange[0].toLocaleString("en-EU")} – €${f.priceRange[1].toLocaleString(
          "en-EU"
        )}`}
      >
        <Slider
          min={0}
          max={5_000_000}
          step={50_000}
          value={f.priceRange as [number, number]}
          onValueChange={(v) =>
            f.set("priceRange", [v[0], v[1]] as [number, number])
          }
        />
      </FilterGroup>

      <FilterGroup label={`GBA · ${f.m2Range[0]} – ${f.m2Range[1]} m²`}>
        <Slider
          min={0}
          max={2000}
          step={10}
          value={f.m2Range as [number, number]}
          onValueChange={(v) =>
            f.set("m2Range", [v[0], v[1]] as [number, number])
          }
        />
      </FilterGroup>

      <FilterGroup
        label={`Min true yield · ${(f.minYield * 100).toFixed(1)}%`}
      >
        <Slider
          min={0}
          max={0.25}
          step={0.005}
          value={[f.minYield]}
          onValueChange={(v) => f.set("minYield", v[0])}
        />
      </FilterGroup>

      <FilterGroup label="Deal status">
        <Select
          value={f.status}
          onValueChange={(v) => f.set("status", v as any)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="approved_candidate">Approved</SelectItem>
            <SelectItem value="manual_review">Manual review</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
      </FilterGroup>

      <FilterGroup label="Acquisition model">
        <Select
          value={f.model}
          onValueChange={(v) => f.set("model", v as any)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Freehold + Lease</SelectItem>
            <SelectItem value="freehold">Freehold only</SelectItem>
            <SelectItem value="lease">Lease only</SelectItem>
          </SelectContent>
        </Select>
      </FilterGroup>

      <FilterGroup label="Building type">
        <Select
          value={f.buildingType ?? "__any"}
          onValueChange={(v) =>
            f.set("buildingType", v === "__any" ? null : v)
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__any">Any</SelectItem>
            {BUILDING_TYPES.map((b) => (
              <SelectItem key={b} value={b}>
                {b}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterGroup>

      <ToggleRow
        label="Loading access only"
        hint="Vehicle / curbside loading required"
        checked={!!f.loadingAccess}
        onChange={(v) => f.set("loadingAccess", v ? true : null)}
      />

      <FilterGroup
        label={`Min ceiling · ${f.minCeilingHeight?.toFixed(1) ?? "—"} m`}
      >
        <Slider
          min={2}
          max={6}
          step={0.1}
          value={[f.minCeilingHeight ?? 2.7]}
          onValueChange={(v) => f.set("minCeilingHeight", v[0])}
        />
      </FilterGroup>

      <div className="flex items-center gap-2 border-t border-border/60 pt-4">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 gap-1.5"
          onClick={() => f.reset()}
        >
          <RotateCcw className="h-3 w-3" />
          Reset
        </Button>
        <Button size="sm" variant="tactical" className="flex-1 gap-1.5">
          <Plus className="h-3 w-3" /> Save preset
        </Button>
      </div>
    </aside>
  );
}

function Header() {
  return (
    <header className="flex items-center justify-between border-b border-border/60 pb-3">
      <div className="flex items-center gap-2">
        <FilterIcon className="h-3.5 w-3.5 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Filters</h3>
      </div>
      <Badge variant="ghost" className="gap-1">
        <SlidersHorizontal className="h-3 w-3" /> 9
      </Badge>
    </header>
  );
}

function FilterGroup({
  label,
  children,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border/60 bg-card/30 px-3 py-2.5">
      <div className="space-y-0.5">
        <div className="text-xs font-medium text-foreground">{label}</div>
        {hint && (
          <div className="text-[10px] text-muted-foreground">{hint}</div>
        )}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
