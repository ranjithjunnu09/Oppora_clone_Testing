import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-tight whitespace-nowrap",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-[var(--color-accent-soft)] text-[var(--color-accent)]",
        neutral:
          "border-[var(--color-border)] bg-[var(--color-surface-2)] text-fg-muted",
        success:
          "border-transparent bg-[color-mix(in_oklch,var(--color-success)_18%,transparent)] text-[var(--color-success)]",
        warning:
          "border-transparent bg-[color-mix(in_oklch,var(--color-warning)_18%,transparent)] text-[var(--color-warning)]",
        danger:
          "border-transparent bg-[color-mix(in_oklch,var(--color-danger)_18%,transparent)] text-[var(--color-danger)]",
        info: "border-transparent bg-[color-mix(in_oklch,var(--color-info)_18%,transparent)] text-[var(--color-info)]",
        outline: "border-[var(--color-border-strong)] text-fg-muted",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
