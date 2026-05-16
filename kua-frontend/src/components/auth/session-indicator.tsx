"use client";

import { LogOut, ShieldCheck, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/providers/auth-provider";

export function SessionIndicator() {
  const { user, logout } = useAuth();
  if (!user) return null;

  const initials = user.displayName
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2 border border-border/60 bg-card/40 hover:bg-card/60"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/15 font-mono text-[10px] font-semibold tracking-wider text-primary">
            {initials}
          </span>
          <span className="hidden text-left sm:flex sm:flex-col sm:leading-tight">
            <span className="text-[11px] font-medium">{user.displayName}</span>
            <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
              {user.clearance}
            </span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Session</DropdownMenuLabel>
        <DropdownMenuItem className="gap-2">
          <User className="h-3.5 w-3.5" /> {user.username}
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-2">
          <ShieldCheck className="h-3.5 w-3.5" /> Clearance · {user.clearance}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => logout()}
          className="gap-2 text-destructive focus:!text-destructive"
        >
          <LogOut className="h-3.5 w-3.5" /> Terminate session
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
