import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CircleDollarSign, Moon, Server, Sun, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function Header() {
  const { baseUrl, setBaseUrl, theme, toggleTheme } = useAppStore();

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: 4_000,
  });

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-[var(--color-border)] bg-surface px-5">
      {/* ── Base URL input ── */}
      <div className="flex items-center gap-2">
        <Server className="size-3.5 shrink-0 text-fg-subtle" />
        <Input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder={health?.default_base_url ?? "https://api.anthropic.com/v1"}
          className="h-8 w-72 rounded-lg font-mono text-[11px]"
          aria-label="OpenAI-compatible base URL"
        />
        {baseUrl && (
          <Badge variant="info" className="shrink-0">self-hosted</Badge>
        )}
      </div>

      {/* ── Right side ── */}
      <div className="ml-auto flex items-center gap-3">
        {/* Provider status pills */}
        {health?.providers?.map((p) => (
          <Tooltip key={p.id}>
            <TooltipTrigger asChild>
              <Badge
                variant={p.configured ? "success" : p.id === "anthropic" ? "danger" : "neutral"}
                className="cursor-help gap-1.5"
              >
                {!p.configured && <AlertTriangle className="size-3" />}
                <span
                  className={`size-1.5 rounded-full ${p.configured ? "bg-[var(--color-success)] pulse-dot" : "bg-current opacity-50"}`}
                />
                {p.name}
              </Badge>
            </TooltipTrigger>
            <TooltipContent className="max-w-64 text-xs">
              {p.configured ? (
                <>{p.env_key} is configured.{p.notes && ` ${p.notes}`}</>
              ) : p.id === "anthropic" ? (
                <>{p.env_key} not set — Claude models can't run. Add it to .env and restart.</>
              ) : (
                <>{p.env_key} not set. Claude still works; you lose the OpenAI baseline.</>
              )}
            </TooltipContent>
          </Tooltip>
        ))}

        {/* Live stats */}
        {stats && (
          <>
            <Separator orientation="vertical" className="h-5" />
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex cursor-default items-center gap-1.5 text-xs">
                  <CircleDollarSign className="size-3.5 text-fg-subtle" />
                  <span className="tnum font-medium text-fg">{formatCost(stats.total_cost_usd)}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>Total spend across all recorded runs</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex cursor-default items-center gap-1.5 text-xs">
                  <Zap className="size-3.5 text-fg-subtle" />
                  <span className="tnum font-medium text-fg">{formatTokens(stats.total_tokens)}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {stats.total_calls} LLM calls across {stats.total_runs} runs
              </TooltipContent>
            </Tooltip>
          </>
        )}

        <Separator orientation="vertical" className="h-5" />

        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          className="rounded-lg"
        >
          {theme === "dark" ? (
            <Sun className="size-4 text-fg-muted" />
          ) : (
            <Moon className="size-4 text-fg-muted" />
          )}
        </Button>
      </div>
    </header>
  );
}
