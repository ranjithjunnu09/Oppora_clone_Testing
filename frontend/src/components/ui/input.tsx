import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1 text-sm text-fg transition-colors",
        "placeholder:text-fg-subtle",
        "focus-visible:border-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-accent)]",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm leading-relaxed text-fg transition-colors resize-y",
      "placeholder:text-fg-subtle",
      "focus-visible:border-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-accent)]",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    style={{ overflowWrap: "break-word", wordBreak: "break-word", overflowX: "hidden" }}
    {...props}
  />
));
Textarea.displayName = "Textarea";
