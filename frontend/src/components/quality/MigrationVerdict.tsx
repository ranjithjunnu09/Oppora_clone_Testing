import { AlertTriangle, ArrowRight, Check, HelpCircle, X } from "lucide-react";
import type { ModelAggregate, Run } from "@/lib/types";
import { cn, formatCost, formatLatency } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** How far below baseline quality we still call acceptable. */
const QUALITY_TOLERANCE = 3;
/** Below this pass rate the model is not shippable regardless of mean score. */
const MIN_PASS_RATE = 95;

type Verdict = "ship" | "risky" | "no" | "baseline" | "unknown";

const VERDICT_META: Record<Verdict, { label: string; badge: "success" | "warning" | "danger" | "neutral"; icon: typeof Check }> = {
  ship: { label: "Quality held", badge: "success", icon: Check },
  risky: { label: "Inconsistent", badge: "warning", icon: AlertTriangle },
  no: { label: "Quality dropped", badge: "danger", icon: X },
  baseline: { label: "Baseline", badge: "neutral", icon: ArrowRight },
  unknown: { label: "No rubric", badge: "neutral", icon: HelpCircle },
};

function verdictFor(row: ModelAggregate, baselineQuality: number | null, isBaseline: boolean): Verdict {
  if (isBaseline) return "baseline";
  if (row.quality_mean === null || baselineQuality === null) return "unknown";
  if (row.failed > 0) return "no";

  const heldMean = row.quality_mean >= baselineQuality - QUALITY_TOLERANCE;
  const consistent = (row.pass_rate ?? 0) >= MIN_PASS_RATE;

  if (heldMean && consistent) return "ship";
  // Averages fine but swings — the worst run is what ships, so this is not a pass.
  if (heldMean && !consistent) return "risky";
  return "no";
}

/**
 * The migration decision surface: did quality hold, and how much did it save?
 *
 * Deliberately reports the WORST observed run beside the mean. A model
 * averaging 78 across 100/40/95 is not safe to ship, and a mean alone hides
 * exactly that.
 */
export function MigrationVerdict({
  byModel,
  runs,
  baseline,
}: {
  byModel: ModelAggregate[];
  runs: Run[];
  baseline: Run | null;
}) {
  if (byModel.length < 2) return null;

  // Prefer an explicitly pinned baseline; otherwise use the first model run.
  const baselineModel =
    baseline && byModel.some((m) => m.model === baseline.model)
      ? baseline.model
      : byModel[0].model;

  const baseRow = byModel.find((m) => m.model === baselineModel) ?? byModel[0];
  const baseQuality = baseRow.quality_mean;
  const baseCost = baseRow.cost_mean;

  const anyRepeats = byModel.some((m) => m.repeats > 1);

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-baseline gap-2">
          <p className="text-sm font-semibold text-fg">Migration readiness</p>
          <p className="text-[11px] text-fg-muted">
            vs <span className="font-mono">{baselineModel}</span>
            {baseline ? " (pinned)" : " (first run)"}
          </p>
          {!anyRepeats && (
            <Badge variant="warning" className="ml-auto">
              1 run each — not yet evidence
            </Badge>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-fg-subtle">
                <th className="px-2 py-2 font-medium">Model</th>
                <th className="px-2 py-2 text-right font-medium">Quality</th>
                <th className="px-2 py-2 text-right font-medium">
                  <Tooltip>
                    <TooltipTrigger className="cursor-help underline decoration-dotted">
                      Worst
                    </TooltipTrigger>
                    <TooltipContent>
                      Lowest score across repeats. This is the run that ships on a bad day, so it
                      matters more than the mean.
                    </TooltipContent>
                  </Tooltip>
                </th>
                <th className="px-2 py-2 text-right font-medium">
                  <Tooltip>
                    <TooltipTrigger className="cursor-help underline decoration-dotted">
                      Clean
                    </TooltipTrigger>
                    <TooltipContent>
                      Share of repeats with zero critical rule failures.
                    </TooltipContent>
                  </Tooltip>
                </th>
                <th className="px-2 py-2 text-right font-medium">Cost/run</th>
                <th className="px-2 py-2 text-right font-medium">Saving</th>
                <th className="px-2 py-2 text-right font-medium">Latency</th>
                <th className="px-2 py-2 text-right font-medium">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {byModel.map((row) => {
                const isBase = row.model === baselineModel;
                const verdict = verdictFor(row, baseQuality, isBase);
                const meta = VERDICT_META[verdict];
                const Icon = meta.icon;

                const saving =
                  baseCost > 0 && !isBase
                    ? ((baseCost - row.cost_mean) / baseCost) * 100
                    : null;
                const qualityDelta =
                  baseQuality !== null && row.quality_mean !== null && !isBase
                    ? row.quality_mean - baseQuality
                    : null;

                return (
                  <tr
                    key={row.model}
                    className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-2)]"
                  >
                    <td className="px-2 py-2">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-[11px] text-fg">{row.model}</span>
                        {row.provider === "anthropic" && (
                          <Badge variant="neutral" className="px-1 py-0 text-[9px]">
                            compat
                          </Badge>
                        )}
                        {row.degraded > 0 && (
                          <Badge variant="warning" className="px-1 py-0 text-[9px]">
                            {row.degraded} partial
                          </Badge>
                        )}
                        {row.failed > 0 && (
                          <Badge variant="danger" className="px-1 py-0 text-[9px]">
                            {row.failed} failed
                          </Badge>
                        )}
                      </span>
                      {row.stripped_params.length > 0 && (
                        <p className="mt-0.5 text-[9px] text-[var(--color-warning)]">
                          {row.stripped_params.join(", ")} stripped — not parameter-matched
                        </p>
                      )}
                    </td>

                    <td className="tnum px-2 py-2 text-right">
                      {row.quality_mean === null ? (
                        <span className="text-fg-subtle">—</span>
                      ) : (
                        <span className="text-fg">
                          {row.quality_mean}
                          {qualityDelta !== null && (
                            <span
                              className={cn(
                                "ml-1 text-[10px]",
                                qualityDelta >= 0
                                  ? "text-[var(--color-success)]"
                                  : "text-[var(--color-danger)]",
                              )}
                            >
                              {qualityDelta > 0 ? "+" : ""}
                              {qualityDelta.toFixed(0)}
                            </span>
                          )}
                        </span>
                      )}
                    </td>

                    <td className="tnum px-2 py-2 text-right text-fg-muted">
                      {row.quality_min ?? "—"}
                    </td>

                    <td className="tnum px-2 py-2 text-right">
                      {row.pass_rate === null ? (
                        <span className="text-fg-subtle">—</span>
                      ) : (
                        <span
                          className={
                            row.pass_rate >= MIN_PASS_RATE
                              ? "text-[var(--color-success)]"
                              : "text-[var(--color-warning)]"
                          }
                        >
                          {row.pass_rate}%
                        </span>
                      )}
                    </td>

                    <td className="tnum px-2 py-2 text-right text-fg-muted">
                      {formatCost(row.cost_mean)}
                    </td>

                    <td className="tnum px-2 py-2 text-right">
                      {saving === null ? (
                        <span className="text-fg-subtle">—</span>
                      ) : (
                        <span
                          className={
                            saving > 0
                              ? "text-[var(--color-success)]"
                              : "text-[var(--color-warning)]"
                          }
                        >
                          {saving > 0 ? "−" : "+"}
                          {Math.abs(saving).toFixed(0)}%
                        </span>
                      )}
                    </td>

                    <td className="tnum px-2 py-2 text-right text-fg-muted">
                      {formatLatency(row.latency_mean)}
                    </td>

                    <td className="px-2 py-2 text-right">
                      <Badge variant={meta.badge}>
                        <Icon className="size-3" />
                        {meta.label}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="text-[10px] leading-relaxed text-fg-subtle">
          "Quality held" means mean score within {QUALITY_TOLERANCE} points of baseline AND at least{" "}
          {MIN_PASS_RATE}% of repeats free of critical failures. Cost figures come from the price
          table, so a self-hosted model shows $0 and its real saving depends on your own serving
          cost — compare tokens and latency instead.
          {runs.length > 0 && ` Based on ${runs.length} run${runs.length === 1 ? "" : "s"}.`}
        </p>
      </CardContent>
    </Card>
  );
}
