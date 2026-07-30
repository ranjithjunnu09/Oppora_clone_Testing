import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, History, Layers, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Feature } from "@/lib/types";
import {
  cn,
  formatCost,
  formatLatency,
  formatRelativeTime,
  formatTokens,
} from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const STATUS_VARIANT = {
  succeeded: "success",
  degraded: "warning",
  failed: "danger",
  running: "info",
} as const;

const STATUS_DOT: Record<string, string> = {
  succeeded: "bg-[var(--color-success)]",
  degraded:  "bg-[var(--color-warning)]",
  failed:    "bg-[var(--color-danger)]",
  running:   "bg-[var(--color-info)] pulse-dot",
};

export function HistoryPage() {
  const queryClient = useQueryClient();
  const [featureFilter, setFeatureFilter] = useState<string>("all");

  const { data: featuresData } = useQuery({ queryKey: ["features"], queryFn: api.features });
  const { data, isLoading } = useQuery({
    queryKey: ["history", featureFilter],
    queryFn: () => api.history(featureFilter === "all" ? undefined : featureFilter),
    refetchInterval: 5_000,
  });

  const clear = useMutation({
    mutationFn: api.clearHistory,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      toast.success("History cleared");
    },
  });

  const nameOf = (id: string) =>
    featuresData?.features.find((f: Feature) => f.id === id)?.name ?? id;

  const runs = data?.runs ?? [];

  return (
    <div style={{ height: "100%", overflow: "hidden" }}>
    <ScrollArea style={{ height: "100%" }}>
      <div className="space-y-5 p-6">
        {/* ── Header ── */}
        <div className="flex flex-wrap items-start gap-3">
          <div className="space-y-1">
            <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-fg">
              <History className="size-5 text-[var(--color-accent)]" />
              Run history
            </h1>
            <p className="text-xs text-fg-muted">
              Every run is persisted to SQLite — baselines captured today are still here next week.
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
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
            <Button
              variant="secondary"
              size="icon"
              onClick={() => clear.mutate()}
              disabled={clear.isPending || runs.length === 0}
              aria-label="Clear history"
              className="h-8 w-8 rounded-lg"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>

        {/* ── Summary strip ── */}
        {runs.length > 0 && (
          <div className="grid grid-cols-3 gap-3">
            {[
              {
                label: "Total runs",
                value: runs.length.toString(),
                icon: <Layers className="size-3.5 text-[var(--color-accent)]" />,
              },
              {
                label: "Avg latency",
                value: runs.length
                  ? formatLatency(
                      runs.reduce((s, r) => s + r.total_latency_ms, 0) / runs.length,
                    )
                  : "—",
                icon: <Clock className="size-3.5 text-[var(--color-info)]" />,
              },
              {
                label: "Total tokens",
                value: formatTokens(
                  runs.reduce((s, r) => s + r.total_prompt_tokens + r.total_completion_tokens, 0),
                ),
                icon: <Zap className="size-3.5 text-[var(--color-success)]" />,
              },
            ].map(({ label, value, icon }) => (
              <Card key={label}>
                <CardContent className="flex items-center gap-3 p-4">
                  {icon}
                  <div>
                    <p className="text-[10px] text-fg-subtle">{label}</p>
                    <p className="font-mono text-sm font-semibold tabular-nums text-fg">{value}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* ── Table ── */}
        {!isLoading && runs.length === 0 ? (
          <EmptyState
            icon={History}
            title="No runs yet"
            description="Run any feature and it will appear here with its full token and cost breakdown."
          />
        ) : (
          <Card className="overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-surface-2 text-left">
                  {["When", "Feature", "Model", "Status", "Calls", "Tokens", "Latency", "Cost"].map(
                    (h, i) => (
                      <th
                        key={h}
                        className={cn(
                          "px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle",
                          i >= 4 && "text-right",
                        )}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {isLoading
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-b border-[var(--color-border)]">
                        <td colSpan={8} className="px-4 py-3">
                          <div className="shimmer relative h-4 w-full rounded-md bg-surface-2" />
                        </td>
                      </tr>
                    ))
                  : runs.map((r) => (
                      <tr
                        key={r.id}
                        className="border-b border-[var(--color-border)] last:border-0 transition-colors hover:bg-surface-2"
                      >
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-[11px] text-fg-subtle">
                          {formatRelativeTime(r.created_at)}
                        </td>
                        <td className="max-w-[180px] truncate px-4 py-3 font-medium text-fg">
                          {nameOf(r.feature_id)}
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-fg-muted">{r.model}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <span className={cn("size-1.5 rounded-full", STATUS_DOT[r.status])} />
                            <Badge variant={STATUS_VARIANT[r.status]}>{r.status}</Badge>
                          </div>
                        </td>
                        <td className="tnum px-4 py-3 text-right text-fg-muted">{r.call_count}</td>
                        <td className="tnum px-4 py-3 text-right text-fg-muted">
                          {formatTokens(r.total_prompt_tokens + r.total_completion_tokens)}
                        </td>
                        <td className="tnum px-4 py-3 text-right text-fg-muted">
                          {formatLatency(r.total_latency_ms)}
                        </td>
                        <td className="tnum px-4 py-3 text-right font-medium text-fg">
                          {formatCost(r.total_cost_usd)}
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </ScrollArea>
    </div>
  );
}
