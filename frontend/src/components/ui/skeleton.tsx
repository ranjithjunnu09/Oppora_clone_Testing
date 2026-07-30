import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "shimmer relative overflow-hidden rounded-md bg-[var(--color-surface-2)]",
        className,
      )}
      {...props}
    />
  );
}
