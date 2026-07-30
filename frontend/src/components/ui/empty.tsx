import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--color-border-strong)] px-6 py-14 text-center",
        className,
      )}
    >
      <div className="flex size-10 items-center justify-center rounded-lg bg-[var(--color-surface-2)]">
        <Icon className="size-5 text-fg-subtle" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-fg">{title}</p>
        {description && <p className="max-w-sm text-xs text-fg-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
