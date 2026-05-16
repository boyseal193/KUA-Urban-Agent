"use client";

import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      theme="dark"
      richColors={false}
      toastOptions={{
        unstyled: false,
        classNames: {
          toast:
            "!bg-card/90 !backdrop-blur-xl !border !border-border/70 !text-foreground !shadow-panel !rounded-lg",
          title: "!text-sm !font-semibold",
          description: "!text-xs !text-muted-foreground",
          actionButton: "!bg-primary/20 !text-primary !border !border-primary/40",
          success: "!border-accent/40",
          error: "!border-destructive/40",
        },
      }}
    />
  );
}
