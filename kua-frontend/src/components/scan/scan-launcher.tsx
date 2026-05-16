"use client";

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Play, RefreshCcw, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";

import { useAutoScan } from "@/hooks/use-scan";
import { PROPERTY_TYPES } from "@/lib/constants";
import { ScanProgress } from "./scan-progress";
import type { AutoScanFilters } from "@/lib/api/types";

const schema = z.object({
  city_slug: z.string().default("barcelona-barcelona"),
  max_price: z.number().min(50_000).max(10_000_000),
  min_m2: z.number().min(50).max(2000),
  max_m2: z.number().min(50).max(2000),
  property_types: z.array(z.string()).min(1),
  ground_floor_only: z.boolean(),
  sale_only: z.boolean(),
  limit: z.number().min(1).max(50),
  generate_excel: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const defaults: FormValues = {
  city_slug: "barcelona-barcelona",
  max_price: 1_000_000,
  min_m2: 200,
  max_m2: 300,
  property_types: ["locales", "naves"],
  ground_floor_only: true,
  sale_only: true,
  limit: 10,
  generate_excel: true,
};

export function ScanLauncher() {
  const scan = useAutoScan();
  const { control, handleSubmit, register, watch, reset } = useForm<FormValues>(
    {
      resolver: zodResolver(schema),
      defaultValues: defaults,
    }
  );

  const values = watch();

  const onSubmit = async (v: FormValues) => {
    try {
      const payload: AutoScanFilters = { ...v };
      const res = await scan.mutateAsync(payload);
      toast.success("Scan complete", {
        description: `${res.scanned_count} listings ingested · ${res.approved_candidates_count} approved`,
      });
    } catch (e: any) {
      toast.error("Scan failed", { description: e?.message ?? "Unknown error" });
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="panel space-y-5 p-5"
      >
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings2 className="h-3.5 w-3.5 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">
              Scan Parameters
            </h3>
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              reset(defaults);
              scan.reset();
            }}
            className="gap-1.5"
          >
            <RefreshCcw className="h-3 w-3" /> Reset
          </Button>
        </header>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Field label="City slug">
            <Input
              {...register("city_slug")}
              placeholder="barcelona-barcelona"
              className="font-mono"
            />
          </Field>

          <Field label={`Limit · ${values.limit}`}>
            <Controller
              control={control}
              name="limit"
              render={({ field }) => (
                <Slider
                  min={1}
                  max={50}
                  step={1}
                  value={[field.value]}
                  onValueChange={(v) => field.onChange(v[0])}
                />
              )}
            />
          </Field>

          <Field
            label={`Max price · €${values.max_price.toLocaleString("en-EU")}`}
          >
            <Controller
              control={control}
              name="max_price"
              render={({ field }) => (
                <Slider
                  min={100_000}
                  max={5_000_000}
                  step={50_000}
                  value={[field.value]}
                  onValueChange={(v) => field.onChange(v[0])}
                />
              )}
            />
          </Field>

          <Field
            label={`GBA range · ${values.min_m2} – ${values.max_m2} m²`}
          >
            <Controller
              control={control}
              name="min_m2"
              render={({ field: minF }) => (
                <Controller
                  control={control}
                  name="max_m2"
                  render={({ field: maxF }) => (
                    <Slider
                      min={50}
                      max={1500}
                      step={10}
                      value={[minF.value, maxF.value]}
                      onValueChange={(v) => {
                        const [a, b] = v;
                        minF.onChange(Math.min(a, b));
                        maxF.onChange(Math.max(a, b));
                      }}
                    />
                  )}
                />
              )}
            />
          </Field>

          <Field label="Property types">
            <Controller
              control={control}
              name="property_types"
              render={({ field }) => (
                <div className="grid grid-cols-2 gap-2">
                  {PROPERTY_TYPES.map((pt) => {
                    const checked = field.value.includes(pt.value);
                    return (
                      <label
                        key={pt.value}
                        className="flex cursor-pointer items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-2 text-xs hover:border-primary/40"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(c) => {
                            const next = c
                              ? [...field.value, pt.value]
                              : field.value.filter((v) => v !== pt.value);
                            field.onChange(next);
                          }}
                        />
                        {pt.label}
                      </label>
                    );
                  })}
                </div>
              )}
            />
          </Field>

          <div className="space-y-3">
            <Field label="Constraints" />
            <ToggleRow
              label="Ground floor only"
              hint="Eliminates upper-floor logistics overhead"
            >
              <Controller
                control={control}
                name="ground_floor_only"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
            </ToggleRow>
            <ToggleRow
              label="Sale only"
              hint="Exclude lease/rent-only listings"
            >
              <Controller
                control={control}
                name="sale_only"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
            </ToggleRow>
            <ToggleRow
              label="Generate Excel"
              hint="Auto-export full underwriting workbook"
            >
              <Controller
                control={control}
                name="generate_excel"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
            </ToggleRow>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border/60 pt-4">
          <p className="text-[11px] text-muted-foreground">
            Calls{" "}
            <code className="rounded bg-white/[0.04] px-1 py-px font-mono text-[10px]">
              POST /scan/idealista/auto
            </code>{" "}
            via secure proxy.
          </p>
          <Button
            type="submit"
            variant="default"
            size="lg"
            disabled={scan.isPending}
            className="gap-2 font-mono uppercase tracking-[0.2em] text-[11px]"
          >
            <Play className="h-3.5 w-3.5" />
            {scan.isPending ? "Scanning…" : "Initiate Scan"}
          </Button>
        </div>
      </form>

      <div className="space-y-4">
        <ScanProgress
          phase={scan.phase}
          progress={scan.progress}
          scannedCount={scan.data?.scanned_count}
          approvedCount={scan.data?.approved_candidates_count}
          error={scan.error?.message}
        />
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: React.ReactNode;
  children?: React.ReactNode;
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
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border/60 bg-card/30 px-3 py-2">
      <div className="space-y-0.5">
        <div className="text-xs font-medium text-foreground">{label}</div>
        {hint && (
          <div className="text-[10px] text-muted-foreground">{hint}</div>
        )}
      </div>
      {children}
    </div>
  );
}
