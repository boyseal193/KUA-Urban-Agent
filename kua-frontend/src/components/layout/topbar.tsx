"use client";

import * as React from "react";
import { Bell, Command, Menu, Search } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/common/status-pill";
import { SessionIndicator } from "@/components/auth/session-indicator";
import { useAuth } from "@/providers/auth-provider";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { MobileSidebar } from "./sidebar";

export function Topbar() {
  const { user } = useAuth();
  const [time, setTime] = React.useState<string>("");

  React.useEffect(() => {
    const t = () => setTime(new Date().toUTCString().slice(17, 25) + " UTC");
    t();
    const id = setInterval(t, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border/60 bg-background/70 px-4 backdrop-blur-xl sm:px-6">
      <MobileNavTrigger />

      <div className="relative hidden flex-1 max-w-xl sm:block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search address, neighbourhood, deal ID…"
          className="h-9 pl-9 pr-16 font-mono text-xs tracking-wider bg-card/40"
        />
        <kbd className="absolute right-2 top-1/2 hidden -translate-y-1/2 items-center gap-1 rounded border border-border/60 bg-white/[0.04] px-1.5 py-px font-mono text-[10px] text-muted-foreground sm:inline-flex">
          <Command className="h-2.5 w-2.5" /> K
        </kbd>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <StatusPill
          label={`SECTOR · BARCELONA`}
          color="#38E1FF"
          pulse={false}
          className="hidden md:inline-flex"
        />
        <StatusPill
          label={time || "—"}
          color="#7CFAB3"
          className="hidden sm:inline-flex"
        />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Notifications"
          className="relative border border-border/60 bg-card/40"
        >
          <Bell className="h-3.5 w-3.5" />
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -right-px -top-px h-2 w-2 rounded-full bg-accent shadow-glow-neon"
          />
        </Button>
        {user && <SessionIndicator />}
      </div>
    </header>
  );
}

function MobileNavTrigger() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open navigation"
          className="lg:hidden border border-border/60"
        >
          <Menu className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[260px] p-0">
        <MobileSidebar />
      </SheetContent>
    </Sheet>
  );
}
