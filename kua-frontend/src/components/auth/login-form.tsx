"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Eye, EyeOff, Fingerprint, Loader2, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({
  username: z.string().min(1, "Operator ID required"),
  password: z.string().min(1, "Authorization key required"),
});

type FormValues = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const [show, setShow] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { isSubmitting, errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  async function onSubmit(values: FormValues) {
    setError(null);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.error ?? "Access denied");
      return;
    }

    router.replace(next);
    router.refresh();
  }

  return (
    <motion.form
      onSubmit={handleSubmit(onSubmit)}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
      className="space-y-5"
    >
      <div className="space-y-1.5">
        <Label htmlFor="username">Operator ID</Label>
        <div className="relative">
          <Input
            id="username"
            autoComplete="username"
            placeholder="operator"
            className="pl-9 font-mono tracking-wider"
            {...register("username")}
          />
          <Fingerprint className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        </div>
        {errors.username && (
          <p className="text-[11px] text-destructive">
            {errors.username.message}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="password">Authorization Key</Label>
        <div className="relative">
          <Input
            id="password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            placeholder="••••••••••••"
            className="pl-9 pr-10 font-mono tracking-widest"
            {...register("password")}
          />
          <ShieldCheck className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
          >
            {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
        {errors.password && (
          <p className="text-[11px] text-destructive">
            {errors.password.message}
          </p>
        )}
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.15em] text-destructive"
        >
          <span className="badge-dot bg-destructive shadow-glow-rose" />
          {error}
        </motion.div>
      )}

      <Button
        type="submit"
        variant="default"
        size="lg"
        disabled={isSubmitting}
        className="w-full font-mono uppercase tracking-[0.2em] text-[12px]"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Authenticating
          </>
        ) : (
          <>Establish secure session</>
        )}
      </Button>

      <p className="text-center font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
        ENCRYPTED · TLS 1.3 · JWT · HTTP-ONLY COOKIES
      </p>
    </motion.form>
  );
}
