import { useState } from "react";
import { AlertTriangle, ChevronRight, Database } from "lucide-react";
import type { LLMCall } from "@/lib/types";
import { cn, formatCost, formatLatency, formatTokens } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

/**
 * Per-call breakdown of a run.
 *
 * The point of this view is chained features: when a single "run" is really
 * 8 sequential LLM calls, the aggregate metrics hide which node is slow or
 * expensive. Each row expands to its exact prompt and raw response.
 */
export function CallTimeline({ calls }: { calls: LLMCall[] }) {
  const [open, setOpen] = useState<number | null>(calls.length === 1 ? 0 : null);

  if (!calls.length) {
    return <p className="py-6 text-center text-xs text-fg-subtle">No calls recorded.</p>;
  }

  const maxLatency = Math.max(...calls.map((c) => c.latency_ms), 1);

  return (
    <div className="space-y-1.5">
      {calls.map((call) => {
        const expanded = open === call.index;
        return (
          <div
            key={call.index}
            className={cn(
              "overflow-hidden rounded-lg border transition-colors",
              call.error
                ? "border-[var(--color-danger)]"
                : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]",
            )}
          >
            <button
              type="button"
              onClick={() => setOpen(expanded ? null : call.index)}
              className="flex w-full items-center gap-3 bg-[var(--color-surface-2)] px-3 py-2.5 text-left"
            >
              <ChevronRight
                className={cn(
                  "size-3.5 shrink-0 text-fg-subtle transition-transform",
                  expanded && "rotate-90",
                )}
              />
              <span className="w-14 shrink-0 text-xs font-medium text-fg">{call.label}</span>

              {/* Latency bar, scaled against the slowest call in the run. */}
              <div className="hidden h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--color-border)] sm:block">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${(call.latency_ms / maxLatency) * 100}%` }}
                />
              </div>

              <div className="flex shrink-0 items-center gap-3 text-[11px]">
                {call.error ? (
                  <Badge variant="danger">
                    <AlertTriangle className="size-3" />
                    failed
                  </Badge>
                ) : (
                  <>
                    {call.cached_tokens > 0 && (
                      <span className="hidden items-center gap-1 text-[var(--color-success)] md:inline-flex">
                        <Database className="size-3" />
                        {call.cache_hit_rate.toFixed(0)}%
                      </span>
                    )}
                    {call.stripped_params?.length > 0 && (
                      <Badge
                        variant="warning"
                        title={`Dropped before the call because this provider rejects it: ${call.stripped_params.join(", ")}`}
                      >
                        {call.stripped_params.join(", ")} stripped
                      </Badge>
                    )}
                    {call.reasoning_tokens > 0 && (
                      <Badge variant="warning" className="hidden md:inline-flex">
                        {formatTokens(call.reasoning_tokens)} reasoning
                      </Badge>
                    )}
                    <span className="tnum hidden text-fg-muted lg:inline">
                      {formatTokens(call.prompt_tokens)} in / {formatTokens(call.completion_tokens)}{" "}
                      out
                    </span>
                    <span className="tnum w-14 text-right text-fg-muted">
                      {formatLatency(call.latency_ms)}
                    </span>
                    <span className="tnum w-16 text-right text-fg-subtle">
                      {formatCost(call.cost_usd)}
                    </span>
                  </>
                )}
              </div>
            </button>

            {expanded && (
              <div className="space-y-3 border-t border-[var(--color-border)] bg-surface p-3">
                {call.error && (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-[color-mix(in_oklch,var(--color-danger)_10%,transparent)] p-3 font-mono text-[11px] text-[var(--color-danger)]">
                    {call.error}
                  </pre>
                )}

                {call.messages.map((m, i) => (
                  <div key={i} className="space-y-1">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
                      {m.role}
                    </p>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 font-mono text-[11px] leading-relaxed text-fg-muted">
                      {m.content}
                    </pre>
                  </div>
                ))}

                {call.response_text && (
                  <div className="space-y-1">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-accent)]">
                      response
                    </p>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--color-accent-soft)] bg-[var(--color-surface-2)] p-2.5 font-mono text-[11px] leading-relaxed text-fg">
                      {call.response_text}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
