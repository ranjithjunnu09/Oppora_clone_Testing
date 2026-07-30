import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Filter,
  MessageSquare,
  RefreshCw,
  ScrollText,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Feature } from "@/lib/types";
import { cn, formatCost, formatLatency, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LogEntry {
  run_id: string;
  feature_id: string;
  batch_id: string | null;
  run_status: "running" | "succeeded" | "degraded" | "failed";
  run_created_at: number;
  run_error: string | null;
  call_index: number;
  call_label: string;
  model: string;
  provider: string;
  latency_ms: number;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cache_hit_rate: number;
  stripped_params: string[];
  messages: { role: string; content: string }[];
  response_text: string | null;
  error: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_BADGE = {
  succeeded: "success",
  degraded:  "warning",
  failed:    "danger",
  running:   "info",
} as const;

const STATUS_ICON = {
  succeeded: <CheckCircle2 className="size-3.5 text-[var(--color-success)]" />,
  degraded:  <AlertTriangle className="size-3.5 text-[var(--color-warning)]" />,
  failed:    <AlertCircle   className="size-3.5 text-[var(--color-danger)]" />,
  running:   <Activity      className="size-3.5 pulse-dot text-[var(--color-info)]" />,
};

function RoleChip({ role }: { role: string }) {
  const style: Record<string, string> = {
    system:    "bg-[var(--color-accent-soft)]  text-[var(--color-accent)]",
    user:      "bg-surface-2 text-fg-muted",
    assistant: "bg-[var(--color-success-soft)] text-[var(--color-success)]",
  };
  return (
    <span className={cn(
      "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider",
      style[role] ?? "bg-surface-2 text-fg-muted",
    )}>
      {role}
    </span>
  );
}

function MessageBlock({ msg }: { msg: { role: string; content: string } }) {
  const [collapsed, setCollapsed] = useState(msg.content.length > 500);
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <RoleChip role={msg.role} />
        <span className="text-[10px] text-fg-subtle">{msg.content.length} chars</span>
      </div>
      <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--color-border)] bg-canvas px-3 py-2.5 font-mono text-[11px] leading-relaxed text-fg-muted">
        {collapsed ? msg.content.slice(0, 500) + "…" : msg.content}
      </pre>
      {msg.content.length > 500 && (
        <button
          className="text-[10px] text-[var(--color-accent)] hover:underline"
          onClick={() => setCollapsed((v) => !v)}
        >
          {collapsed ? "Show full" : "Collapse"}
        </button>
      )}
    </div>
  );
}

function LogRow({ entry, nameOf }: { entry: LogEntry; nameOf: (id: string) => string }) {
  const [expanded, setExpanded] = useState(false);
  const hasError = !!entry.error;

  return (
    <div className={cn(
      "border-b border-[var(--color-border)] last:border-0 transition-colors",
      hasError && "bg-[oklch(0.15_0.04_25/0.35)]",
      !hasError && expanded && "bg-surface-2",
    )}>
      {/* ── Collapsed row ── */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-2 transition-colors"
      >
        <span className="text-fg-subtle">
          {expanded
            ? <ChevronDown className="size-3.5" />
            : <ChevronRight className="size-3.5" />}
        </span>

        {/* Status */}
        <span>
          {hasError
            ? <AlertCircle className="size-3.5 text-[var(--color-danger)]" />
            : STATUS_ICON[entry.run_status]}
        </span>

        <span className="w-24 shrink-0 font-mono text-[11px] text-fg-subtle">
          {formatRelativeTime(entry.run_created_at)}
        </span>

        <span className="w-44 shrink-0 truncate text-[12px] font-medium text-fg">
          {nameOf(entry.feature_id)}
        </span>

        <span className="w-16 shrink-0 text-[11px] text-fg-subtle">{entry.call_label}</span>

        <span className="flex-1 truncate font-mono text-[11px] text-fg-muted">{entry.model}</span>

        <span className="flex shrink-0 items-center gap-1 text-[11px] text-fg-subtle">
          <Clock className="size-3" />
          {formatLatency(entry.latency_ms)}
        </span>

        <span className="flex w-16 shrink-0 items-center justify-end gap-1 font-mono text-[11px] text-fg-subtle">
          <Zap className="size-3" />
          {entry.total_tokens > 0 ? entry.total_tokens.toLocaleString() : "—"}
        </span>

        <span className="w-20 shrink-0 text-right font-mono text-[11px] text-fg">
          {entry.cost_usd > 0 ? formatCost(entry.cost_usd) : <span className="text-fg-subtle">$—</span>}
        </span>

        <div className="flex w-28 shrink-0 items-center justify-end gap-1">
          {hasError && <Badge variant="danger">error</Badge>}
          {entry.stripped_params.length > 0 && (
            <Badge variant="warning" title={`Stripped: ${entry.stripped_params.join(", ")}`}>
              stripped
            </Badge>
          )}
          {entry.cache_hit_rate > 0.5 && <Badge variant="info">cached</Badge>}
        </div>
      </button>

      {/* ── Expanded detail ── */}
      {expanded && (
        <div className="border-t border-[var(--color-border)] bg-canvas px-5 pb-5 pt-4 space-y-4 fade-in">

          {/* Error */}
          {hasError && (
            <div className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] px-4 py-3">
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-danger)]">
                <AlertCircle className="size-3.5" /> Error
              </p>
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[var(--color-danger)]/80">
                {entry.error}
              </pre>
            </div>
          )}

          {/* Metrics */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: "Latency",    value: formatLatency(entry.latency_ms) },
              { label: "Tokens",     value: `${entry.prompt_tokens} → ${entry.completion_tokens}` },
              { label: "Cache",      value: entry.cached_tokens > 0 ? `${Math.round(entry.cache_hit_rate * 100)}%` : "—" },
              { label: "Cost",       value: formatCost(entry.cost_usd) },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg border border-[var(--color-border)] bg-surface px-3 py-2.5">
                <p className="text-[10px] text-fg-subtle">{label}</p>
                <p className="mt-0.5 font-mono text-xs font-semibold text-fg">{value}</p>
              </div>
            ))}
          </div>

          {/* Stripped params warning */}
          {entry.stripped_params.length > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-soft)] px-3 py-2 text-xs text-[var(--color-warning)]">
              <AlertTriangle className="size-3.5 shrink-0" />
              Stripped before sending:
              <code className="font-mono font-medium">{entry.stripped_params.join(", ")}</code>
            </div>
          )}

          {/* Prompt messages */}
          {entry.messages.length > 0 && (
            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
                <MessageSquare className="size-3.5" />
                Prompt ({entry.messages.length})
              </p>
              <div className="space-y-2">
                {entry.messages.map((msg, i) => (
                  <MessageBlock key={i} msg={msg} />
                ))}
              </div>
            </div>
          )}

          {/* Response */}
          {entry.response_text && (
            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
                <Activity className="size-3.5" />
                Response
              </p>
              <pre className="max-h-52 overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-[var(--color-success)]/25 bg-[var(--color-success-soft)] px-3 py-2.5 font-mono text-[11px] leading-relaxed text-[var(--color-success)]">
                {entry.response_text}
              </pre>
            </div>
          )}

          {/* IDs */}
          <div className="flex flex-wrap items-center gap-3 text-[10px] text-fg-subtle">
            <span>Run: <code className="font-mono">{entry.run_id}</code></span>
            {entry.batch_id && <span>Batch: <code className="font-mono">{entry.batch_id}</code></span>}
            <Badge variant={STATUS_BADGE[entry.run_status]} className="ml-auto">{entry.run_status}</Badge>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function LogsPage() {
  const [statusFilter, setStatusFilter] = useState("all");
  const [featureFilter, setFeatureFilter] = useState("all");

  const { data: featuresData } = useQuery({ queryKey: ["features"], queryFn: api.features });

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["logs", featureFilter],
    queryFn: () =>
      api.logs(featureFilter === "all" ? undefined : featureFilter) as Promise<{
        logs: LogEntry[];
        total: number;
      }>,
    refetchInterval: 6_000,
  });

  const nameOf = (id: string) =>
    featuresData?.features.find((f: Feature) => f.id === id)?.name ?? id;

  const allLogs: LogEntry[] = data?.logs ?? [];
  const filtered =
    statusFilter === "all"
      ? allLogs
      : allLogs.filter((e) =>
          statusFilter === "error" ? !!e.error : e.run_status === statusFilter,
        );

  const errorCount  = allLogs.filter((e) => !!e.error).length;
  const totalTokens = allLogs.reduce((s, e) => s + e.total_tokens, 0);
  const totalCost   = allLogs.reduce((s, e) => s + e.cost_usd, 0);

  return (
    <div style={{ height: "100%", overflow: "hidden" }}>
    <ScrollArea style={{ height: "100%" }}>
      <div className="space-y-5 p-6">

        {/* ── Title ── */}
        <div className="flex flex-wrap items-start gap-3">
          <div className="space-y-1">
            <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-fg">
              <ScrollText className="size-5 text-[var(--color-accent)]" />
              Logs
            </h1>
            <p className="text-xs text-fg-muted">
              Every LLM call — prompts, responses, tokens, latency, errors and stripped params.
              Auto-refreshes every 6 s.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="ml-auto h-8 rounded-lg text-xs"
          >
            <RefreshCw className={cn("size-3.5 mr-1.5", isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>

        {/* ── Summary cards ── */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            {
              label:  "Total calls",
              value:  allLogs.length.toString(),
              icon:   <Zap className="size-4 text-[var(--color-accent)]" />,
              accent: false,
            },
            {
              label:  "Errors",
              value:  errorCount.toString(),
              icon:   <AlertCircle className="size-4 text-[var(--color-danger)]" />,
              accent: errorCount > 0,
            },
            {
              label:  "Total tokens",
              value:  totalTokens > 0 ? totalTokens.toLocaleString() : "—",
              icon:   <Activity className="size-4 text-[var(--color-success)]" />,
              accent: false,
            },
            {
              label:  "Total cost",
              value:  formatCost(totalCost),
              icon:   <Coins className="size-4 text-[var(--color-warning)]" />,
              accent: false,
            },
          ].map(({ label, value, icon, accent }) => (
            <Card
              key={label}
              className={cn(accent && "border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)]")}
            >
              <CardHeader className="flex flex-row items-center justify-between pb-1 pt-4 px-4">
                <CardTitle className={cn("text-[11px] font-medium", accent ? "text-[var(--color-danger)]" : "text-fg-subtle")}>
                  {label}
                </CardTitle>
                {icon}
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <p className={cn("font-mono text-2xl font-semibold tabular-nums", accent ? "text-[var(--color-danger)]" : "text-fg")}>
                  {value}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* ── Filters ── */}
        <div className="flex flex-wrap items-center gap-2">
          <Filter className="size-3.5 text-fg-subtle" />
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 w-44 rounded-lg text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="error">Errors only</SelectItem>
              <SelectItem value="succeeded">Succeeded</SelectItem>
              <SelectItem value="degraded">Degraded</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="running">Running</SelectItem>
            </SelectContent>
          </Select>

          <Select value={featureFilter} onValueChange={setFeatureFilter}>
            <SelectTrigger className="h-8 w-52 rounded-lg text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All features</SelectItem>
              {featuresData?.features.map((f) => (
                <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {filtered.length !== allLogs.length && (
            <span className="ml-1 text-[11px] text-fg-subtle">
              {filtered.length} / {allLogs.length} calls
            </span>
          )}
        </div>

        {/* ── Table ── */}
        {!isLoading && filtered.length === 0 ? (
          <EmptyState
            icon={ScrollText}
            title="No logs yet"
            description="Run any feature and every LLM call will appear here with full prompt, response and metrics."
          />
        ) : (
          <Card className="overflow-hidden">
            {/* Column headers */}
            <div className="flex items-center gap-3 border-b border-[var(--color-border)] bg-surface-2 px-4 py-2.5">
              {["", "", "When", "Feature", "Call", "Model", "Latency", "Tokens", "Cost", "Tags"].map(
                (h, i) => (
                  <span
                    key={i}
                    className={cn(
                      "shrink-0 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle",
                      i === 0 && "w-4",
                      i === 1 && "w-4",
                      i === 2 && "w-24",
                      i === 3 && "w-44",
                      i === 4 && "w-16",
                      i === 5 && "flex-1",
                      i >= 6 && "text-right",
                      i === 6 && "w-20",
                      i === 7 && "w-16",
                      i === 8 && "w-20",
                      i === 9 && "w-28",
                    )}
                  >
                    {h}
                  </span>
                ),
              )}
            </div>

            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="shimmer relative overflow-hidden border-b border-[var(--color-border)] px-4 py-3"
                  >
                    <div className="h-4 w-full rounded-md bg-surface-2" />
                  </div>
                ))
              : filtered.map((entry, i) => (
                  <LogRow
                    key={`${entry.run_id}-${entry.call_index}-${i}`}
                    entry={entry}
                    nameOf={nameOf}
                  />
                ))}
          </Card>
        )}

        {allLogs.length > 0 && (
          <p className="text-center text-[10px] text-fg-subtle">
            {allLogs.length} LLM calls · auto-refreshes every 6 seconds
          </p>
        )}
      </div>
    </ScrollArea>
    </div>
  );
}
