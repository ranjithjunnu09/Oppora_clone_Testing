import { Clock, Coins, Database, Hash, Layers } from "lucide-react";
import type { Run } from "@/lib/types";
import { cn, formatCost, formatLatency, formatTokens } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function Metric({
  icon: Icon,
  value,
  label,
  hint,
  accent,
}: {
  icon: typeof Clock;
  value: string;
  label: string;
  hint: string;
  accent?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex min-w-0 flex-1 cursor-help flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            <Icon className="size-3 shrink-0 text-fg-subtle" />
            <span className="truncate text-[10px] uppercase tracking-wide text-fg-subtle">
              {label}
            </span>
          </div>
          <span className={cn("tnum truncate text-lg font-semibold leading-none", accent)}>
            {value}
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  );
}

export function MetricsBar({ run }: { run: Run }) {
  const cacheRate = run.total_prompt_tokens
    ? (run.total_cached_tokens / run.total_prompt_tokens) * 100
    : 0;

  return (
    <div className="flex flex-wrap gap-2">
      <Metric
        icon={Layers}
        label="LLM calls"
        value={String(run.call_count)}
        hint="Number of round trips to the model. Chained features fire several per run."
      />
      <Metric
        icon={Hash}
        label="Input"
        value={formatTokens(run.total_prompt_tokens)}
        hint={`${run.total_prompt_tokens.toLocaleString()} prompt tokens across all calls`}
      />
      <Metric
        icon={Hash}
        label="Output"
        value={formatTokens(run.total_completion_tokens)}
        hint={`${run.total_completion_tokens.toLocaleString()} completion tokens across all calls`}
      />
      <Metric
        icon={Database}
        label="Cached"
        value={`${cacheRate.toFixed(0)}%`}
        accent={
          cacheRate > 40
            ? "text-[var(--color-success)]"
            : cacheRate > 0
              ? "text-[var(--color-warning)]"
              : undefined
        }
        hint="Share of input tokens served from prompt cache. Cached tokens bill at 25%, so a high rate here is the cheapest win available."
      />
      <Metric
        icon={Clock}
        label="Latency"
        value={formatLatency(run.total_latency_ms)}
        hint="Wall-clock time for the whole run, including every chained call."
      />
      <Metric
        icon={Coins}
        label="Cost"
        value={formatCost(run.total_cost_usd)}
        hint="Estimated from the built-in price table. Shows $0 for models with no known pricing, such as self-hosted ones."
      />
    </div>
  );
}
