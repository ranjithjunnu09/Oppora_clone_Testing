import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, Pin, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Feature, Run } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CallTimeline } from "@/components/metrics/CallTimeline";
import { ComparisonChart } from "@/components/metrics/ComparisonChart";
import { MetricsBar } from "@/components/metrics/MetricsBar";
import { ResultRenderer } from "@/components/results/ResultRenderer";
import { MigrationVerdict } from "@/components/quality/MigrationVerdict";
import { QualityPanel } from "@/components/quality/QualityPanel";

function RunView({ run, feature }: { run: Run; feature: Feature }) {
  const queryClient = useQueryClient();
  const pin = useMutation({
    mutationFn: () => api.pinBaseline(run.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["batch"] });
      toast.success(`Pinned ${run.model} as the baseline for this feature`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (run.status === "running") {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-fg-muted">
          <Loader2 className="size-3.5 animate-spin" />
          Running {feature.call_count === "1" ? "1 call" : `${feature.call_count} calls`} on{" "}
          <span className="font-mono">{run.model}</span>…
        </div>
        <div className="flex gap-2">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 flex-1" />
          ))}
        </div>
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (run.status === "failed") {
    return (
      <div className="space-y-3">
        <MetricsBar run={run} />
        <Card className="border-[var(--color-danger)]">
          <CardContent className="space-y-2 p-4">
            <p className="flex items-center gap-2 text-xs font-medium text-[var(--color-danger)]">
              <AlertCircle className="size-4" />
              Run failed
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-[var(--color-surface-2)] p-3 font-mono text-[11px] leading-relaxed text-fg-muted">
              {run.error}
            </pre>
          </CardContent>
        </Card>
        {run.calls && run.calls.length > 0 && <CallTimeline calls={run.calls} />}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <MetricsBar run={run} />

      {run.status === "degraded" && (
        <Card className="border-[var(--color-warning)]">
          <CardContent className="flex gap-2 p-3.5">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-[var(--color-warning)]" />
            <div className="min-w-0 space-y-1">
              <p className="text-xs font-medium text-[var(--color-warning)]">
                Partial failure — do not treat this as a clean result
              </p>
              <p className="text-[11px] leading-relaxed text-fg-muted">{run.error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="output">
        <TabsList>
          <TabsTrigger value="output">Output</TabsTrigger>
          {run.quality && (
            <TabsTrigger value="quality">
              <ShieldCheck className="size-3" />
              Rules
              <Badge
                variant={
                  run.quality.summary.critical > 0
                    ? "danger"
                    : run.quality.summary.failed > 0
                      ? "warning"
                      : "success"
                }
                className="ml-1 px-1 py-0"
              >
                {run.quality.score}
              </Badge>
            </TabsTrigger>
          )}
          <TabsTrigger value="calls">
            Calls
            <Badge variant="neutral" className="ml-1 px-1 py-0">
              {run.call_count}
            </Badge>
          </TabsTrigger>
          <button
            type="button"
            onClick={() => pin.mutate()}
            disabled={pin.isPending || run.is_baseline === 1}
            className="ml-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-fg-subtle transition-colors hover:text-fg disabled:opacity-50"
            title="Pin this run as the reference every other model is measured against"
          >
            <Pin className="size-3" />
            {run.is_baseline === 1 ? "Baseline" : "Pin as baseline"}
          </button>
        </TabsList>
        <TabsContent value="output">
          <ResultRenderer resultType={feature.result_type} result={run.result} />
        </TabsContent>
        {run.quality && (
          <TabsContent value="quality">
            <QualityPanel report={run.quality} />
          </TabsContent>
        )}
        <TabsContent value="calls">
          <CallTimeline calls={run.calls ?? []} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Polls a batch until every run in it settles.
 *
 * Polling rather than streaming is deliberate: the chained features fire up to
 * 8 sequential calls and the batch scorer sends 200 leads in one prompt, both
 * of which outlive a comfortable request timeout. The API runs them on a
 * worker thread and this polls the shared batch id.
 */
export function RunPanel({ batchId, feature }: { batchId: string; feature: Feature }) {
  const { data, isLoading } = useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => api.getBatch(batchId),
    refetchInterval: (q) => (q.state.data?.settled ? false : 900),
  });

  if (isLoading || !data) {
    return <Skeleton className="h-64 w-full" />;
  }

  const multi = data.runs.length > 1;
  // With repeats, the tabs show the first run per model; the aggregate table
  // above already carries the full picture across every repeat.
  const representative = Object.values(
    data.runs.reduce<Record<string, Run>>((acc, r) => {
      if (!acc[r.model] || r.repeat_index < acc[r.model].repeat_index) acc[r.model] = r;
      return acc;
    }, {}),
  );

  return (
    <div className="space-y-4">
      <MigrationVerdict byModel={data.by_model} runs={data.runs} baseline={data.baseline} />
      {multi && <ComparisonChart runs={data.runs} />}

      {multi ? (
        <Tabs defaultValue={representative[0].id}>
          <TabsList className="flex-wrap">
            {representative.map((r) => (
              <TabsTrigger key={r.id} value={r.id}>
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    r.status === "running"
                      ? "animate-pulse bg-[var(--color-warning)]"
                      : r.status === "failed"
                        ? "bg-[var(--color-danger)]"
                        : r.status === "degraded"
                          ? "bg-[var(--color-warning)]"
                          : "bg-[var(--color-success)]",
                  )}
                />
                <span className="font-mono">{r.model}</span>
                {r.quality_score !== null && (
                  <Badge variant="neutral" className="ml-1 px-1 py-0 text-[9px]">
                    {r.quality_score}
                  </Badge>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
          {representative.map((r) => (
            <TabsContent key={r.id} value={r.id}>
              <RunView run={r} feature={feature} />
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <RunView run={data.runs[0]} feature={feature} />
      )}
    </div>
  );
}
