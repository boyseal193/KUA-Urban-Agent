import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-glow hover:brightness-110 active:brightness-95",
        destructive:
          "bg-destructive/90 text-destructive-foreground hover:bg-destructive shadow-glow-rose",
        outline:
          "border border-border bg-transparent text-foreground hover:bg-white/[0.04] hover:border-primary/40",
        secondary:
          "bg-secondary text-secondary-foreground border border-border hover:bg-white/[0.05]",
        ghost: "hover:bg-white/[0.05] text-foreground/80 hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        tactical:
          "bg-card/60 backdrop-blur-xl border border-primary/30 text-primary hover:bg-primary/10 hover:border-primary/60 hover:shadow-glow uppercase tracking-[0.18em] text-[11px] font-mono",
        neon:
          "bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25 hover:shadow-glow-neon uppercase tracking-[0.16em] text-[11px] font-mono",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-lg px-6 text-sm",
        xl: "h-12 rounded-lg px-8 text-sm",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
