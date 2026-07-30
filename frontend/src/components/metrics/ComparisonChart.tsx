import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Run } from "@/lib/types";
import { formatCost, formatLatency, formatTokens, pctDelta } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SERIES = [
  { key: "cost", label: "Cost (USD)", format: formatCost },
  { key: "latency", label: "Latency", format: formatLatency },
  { key: "output", label: "Output tokens", format: formatTokens },
] as const;

const PALETTE = [
  "oklch(0.62 0.19 275)",
  "oklch(0.72 0.17 155)",
  "oklch(0.78 0.16 80)",
  "oklch(0.7 0.14 230)",
  "oklch(0.65 0.2 25)",
];

function ChartCard({
  title,
  data,
  format,
}: {
  title: string;
  data: { model: string; value: number }[];
  format: (n: number) => string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-fg-muted">{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-40 px-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="model"
              tick={{ fontSize: 9, fill: "var(--color-fg-subtle)" }}
              axisLine={false}
              tickLine={false}
              interval={0}
              tickFormatter={(m: string) => (m.length > 14 ? `${m.slice(0, 12)}…` : m)}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "var(--color-fg-subtle)" }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={format}
            />
            <RTooltip
              cursor={{ fill: "var(--color-surface-2)" }}
              contentStyle={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border-strong)",
                borderRadius: 8,
                fontSize: 11,
              }}
              formatter={(v: number) => [format(v), title]}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function ComparisonChart({ runs }: { runs: Run[] }) {
  // Degraded runs carry real token/latency numbers, so they belong on the
  // chart, but the table flags them so nobody reads them as a clean baseline.
  const settled = runs.filter((r) => r.status === "succeeded" || r.status === "degraded");
  if (settled.length < 2) return null;

  const values = {
    cost: settled.map((r) => ({ model: r.model, value: r.total_cost_usd })),
    latency: settled.map((r) => ({ model: r.model, value: r.total_latency_ms })),
    output: settled.map((r) => ({ model: r.model, value: r.total_completion_tokens })),
  };

  // The first run is the baseline everything else is measured against.
  const baseline = settled[0];

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        {SERIES.map((s) => (
          <ChartCard key={s.key} title={s.label} data={values[s.key]} format={s.format} />
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-fg-subtle">
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 text-right font-medium">Calls</th>
                <th className="px-3 py-2 text-right font-medium">Input</th>
                <th className="px-3 py-2 text-right font-medium">Output</th>
                <th className="px-3 py-2 text-right font-medium">Latency</th>
                <th className="px-3 py-2 text-right font-medium">Cost</th>
                <th className="px-3 py-2 text-right font-medium">vs baseline</th>
              </tr>
            </thead>
            <tbody>
              {settled.map((r, i) => {
                const delta = i === 0 ? null : pctDelta(r.total_cost_usd, baseline.total_cost_usd);
                return (
                  <tr
                    key={r.id}
                    className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-2)]"
                  >
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span
                          className="size-2 shrink-0 rounded-full"
                          style={{ background: PALETTE[i % PALETTE.length] }}
                        />
                        <span className="font-mono text-[11px] text-fg">{r.model}</span>
                        {r.status === "degraded" && (
                          <span className="text-[10px] text-[var(--color-warning)]">partial</span>
                        )}
                        {i === 0 && <span className="text-[10px] text-fg-subtle">baseline</span>}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-fg-muted">{r.call_count}</td>
                    <td className="tnum px-3 py-2 text-right text-fg-muted">
                      {formatTokens(r.total_prompt_tokens)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-fg-muted">
                      {formatTokens(r.total_completion_tokens)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-fg-muted">
                      {formatLatency(r.total_latency_ms)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-fg">
                      {formatCost(r.total_cost_usd)}
                    </td>
                    <td className="tnum px-3 py-2 text-right">
                      {delta === null ? (
                        <span className="text-fg-subtle">—</span>
                      ) : (
                        <span
                          className={
                            delta < 0 ? "text-[var(--color-success)]" : "text-[var(--color-warning)]"
                          }
                        >
                          {delta > 0 ? "+" : ""}
                          {delta.toFixed(0)}%
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
