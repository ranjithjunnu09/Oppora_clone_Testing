import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CircleDollarSign,
  ClipboardList,
  Layers,
  Mail,
  Tags,
  Target,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Feature } from "@/lib/types";
import { formatCost, formatTokens } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";

const ICONS: Record<string, LucideIcon> = { Tags, Mail, Target };

/* ── Category metadata ── */
const CAT_META: Record<
  string,
  { color: string; bg: string; border: string; emoji: string; testFirst?: boolean }
> = {
  classification: {
    color:     "text-[var(--color-info)]",
    bg:        "bg-[var(--color-info-soft)]",
    border:    "border-[var(--color-info)]/30",
    emoji:     "🏷️",
  },
  email_generation: {
    color:     "text-[var(--color-accent)]",
    bg:        "bg-[var(--color-accent-soft)]",
    border:    "border-[var(--color-accent)]/30",
    emoji:     "✉️",
    testFirst: true,
  },
  lead_scoring: {
    color:     "text-[var(--color-success)]",
    bg:        "bg-[var(--color-success-soft)]",
    border:    "border-[var(--color-success)]/30",
    emoji:     "🎯",
  },
};

/* ── Workflow steps shown on the dashboard ── */
const WORKFLOW_STEPS = [
  {
    n:    "1",
    icon: ClipboardList,
    title: "Pick a feature",
    desc:  "Choose what you want to test from the left sidebar — classification, email generation, or lead scoring.",
    color: "var(--color-info)",
  },
  {
    n:    "2",
    icon: Tags,
    title: "Fill in sample data",
    desc:  "Each feature has a short form. Paste realistic data from your CRM or use the provided defaults.",
    color: "var(--color-accent)",
  },
  {
    n:    "3",
    icon: Zap,
    title: "Run & compare models",
    desc:  "Hit Run. Select multiple Claude models to see side-by-side output quality, tokens, latency and cost.",
    color: "var(--color-warning)",
  },
  {
    n:    "4",
    icon: CircleDollarSign,
    title: "Read the results",
    desc:  "The right panel shows the AI's output, a quality score (if available), and exact API cost per call.",
    color: "var(--color-success)",
  },
];

/* ── File dependency chain ── */
const FILE_CHAIN = [
  {
    file:   "classification/",
    label:  "Step 1 – Classify",
    desc:   "Company size, industry, email patterns, reply intent",
    color:  "var(--color-info)",
    arrow:  true,
  },
  {
    file:   "lead_scoring/",
    label:  "Step 2 – Score",
    desc:   "Rank leads by fit score so reps focus on the best ones",
    color:  "var(--color-warning)",
    arrow:  true,
  },
  {
    file:   "email_generation/",
    label:  "Step 3 – Outreach",
    desc:   "Generate personalised emails & follow-up sequences",
    color:  "var(--color-accent)",
    arrow:  false,
  },
];

/* ── Sub-components ── */

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  accentColor,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
  accentColor: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-fg-subtle">
            {label}
          </p>
          <div
            className="flex size-7 items-center justify-center rounded-lg"
            style={{ background: `color-mix(in oklch, ${accentColor} 15%, transparent)` }}
          >
            <Icon className="size-3.5" style={{ color: accentColor }} />
          </div>
        </div>
        <p className="tnum text-2xl font-bold leading-none text-fg">{value}</p>
        <p className="mt-1.5 text-[11px] text-fg-subtle">{hint}</p>
      </CardContent>
    </Card>
  );
}

function FeatureCard({ feature, catId }: { feature: Feature; catId: string }) {
  const meta = CAT_META[catId] ?? CAT_META.email_generation;
  return (
    <Link to={`/feature/${feature.id}`} className="group block">
      <div
        className={`
          h-full rounded-xl border bg-surface p-4 transition-all duration-150
          hover:bg-surface-2 hover:shadow-md
          ${meta.border}
        `}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-[13px] font-semibold leading-snug text-fg">{feature.name}</p>
          <ArrowRight
            className={`size-3.5 shrink-0 transition-all duration-150 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 ${meta.color}`}
          />
        </div>
        <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-fg-muted">
          {feature.summary}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Badge variant="neutral" className="font-mono text-[10px]">
            {feature.default_model}
          </Badge>
          {feature.call_count !== "1" && (
            <Badge variant="info">{feature.call_count} AI calls</Badge>
          )}
          {feature.is_reasoning_model && <Badge variant="warning">reasoning</Badge>}
        </div>
      </div>
    </Link>
  );
}

/* ── Page ── */

export function Dashboard() {
  const { data, isLoading } = useQuery({ queryKey: ["features"], queryFn: api.features });
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats });

  return (
    <div style={{ height: "100%", overflow: "hidden" }}>
      <ScrollArea style={{ height: "100%" }}>
        <div className="space-y-10 p-6">

          {/* ══════════════════════════════════════════════════════
              HERO
              ══════════════════════════════════════════════════ */}
          <div className="relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-surface p-7">
            <div className="dot-grid absolute inset-0 opacity-30" />
            <div className="relative space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] px-3 py-1 text-[11px] font-semibold text-[var(--color-accent)]">
                <span className="size-1.5 rounded-full bg-[var(--color-accent)] pulse-dot" />
                Live — Anthropic Claude
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-fg">
                Oppora AI{" "}
                <span className="gradient-text">Benchmark Console</span>
              </h1>
              <p className="max-w-2xl text-[13px] leading-relaxed text-fg-muted">
                Test, compare, and understand how Claude handles Oppora's real AI features —
                classification, email generation, and lead scoring — using the exact same prompts
                as production. No technical knowledge needed to run a test.
              </p>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════
              HOW IT WORKS — 4-step workflow
              ══════════════════════════════════════════════════ */}
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-bold text-fg">How it works</h2>
              <p className="text-[12px] text-fg-subtle">
                4 simple steps to run your first AI benchmark
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {WORKFLOW_STEPS.map((step) => {
                const Icon = step.icon;
                return (
                  <div
                    key={step.n}
                    className="relative rounded-xl border border-[var(--color-border)] bg-surface p-4 space-y-2"
                  >
                    <div className="flex items-center gap-2.5">
                      <div
                        className="flex size-8 shrink-0 items-center justify-center rounded-lg"
                        style={{
                          background: `color-mix(in oklch, ${step.color} 14%, transparent)`,
                        }}
                      >
                        <Icon className="size-4" style={{ color: step.color }} />
                      </div>
                      <span
                        className="text-[10px] font-bold uppercase tracking-widest"
                        style={{ color: step.color }}
                      >
                        Step {step.n}
                      </span>
                    </div>
                    <p className="text-[13px] font-semibold text-fg">{step.title}</p>
                    <p className="text-[11px] leading-relaxed text-fg-muted">{step.desc}</p>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ══════════════════════════════════════════════════════
              FILE DEPENDENCY FLOW
              ══════════════════════════════════════════════════ */}
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-bold text-fg">How the files connect</h2>
              <p className="text-[12px] text-fg-subtle">
                The three categories work together in a pipeline — data flows left to right
              </p>
            </div>
            <div className="flex flex-wrap items-stretch gap-0">
              {FILE_CHAIN.map((step) => (
                <div key={step.file} className="flex items-center">
                  <div
                    className="rounded-xl border p-4 space-y-1.5"
                    style={{
                      borderColor: `color-mix(in oklch, ${step.color} 30%, transparent)`,
                      background:  `color-mix(in oklch, ${step.color} 7%, var(--color-surface))`,
                      minWidth: 180,
                    }}
                  >
                    <p
                      className="text-[10px] font-bold uppercase tracking-widest"
                      style={{ color: step.color }}
                    >
                      {step.label}
                    </p>
                    <p className="font-mono text-[11px] font-semibold text-fg">{step.file}</p>
                    <p className="text-[11px] leading-relaxed text-fg-muted">{step.desc}</p>
                  </div>
                  {step.arrow && (
                    <div className="flex items-center px-2">
                      <ArrowRight className="size-4 text-fg-subtle shrink-0" />
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-surface-2 px-4 py-3">
              <p className="text-[11px] leading-relaxed text-fg-muted">
                <strong className="text-fg">Start with Email Generation</strong> — it's the most
                important feature and uses the largest prompts. Classification and Lead Scoring
                feed data <em>into</em> email generation in the real pipeline.
              </p>
            </div>
          </section>

          {/* ══════════════════════════════════════════════════════
              STATS
              ══════════════════════════════════════════════════ */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Layers}
              label="Features"
              value={String(data?.features.length ?? "—")}
              hint="Across 3 categories"
              accentColor="var(--color-accent)"
            />
            <StatCard
              icon={Zap}
              label="Runs recorded"
              value={String(stats?.total_runs ?? 0)}
              hint={`${stats?.total_calls ?? 0} LLM calls total`}
              accentColor="var(--color-info)"
            />
            <StatCard
              icon={Layers}
              label="Tokens used"
              value={formatTokens(stats?.total_tokens ?? 0)}
              hint="Input + output combined"
              accentColor="var(--color-success)"
            />
            <StatCard
              icon={CircleDollarSign}
              label="Total spend"
              value={formatCost(stats?.total_cost_usd ?? 0)}
              hint="Estimated from price table"
              accentColor="var(--color-warning)"
            />
          </div>

          {/* ══════════════════════════════════════════════════════
              FEATURE CARDS BY CATEGORY
              ══════════════════════════════════════════════════ */}
          {isLoading
            ? [0, 1, 2].map((i) => (
                <div key={i} className="space-y-3">
                  <Skeleton className="h-4 w-40" />
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Skeleton className="h-32" />
                    <Skeleton className="h-32" />
                    <Skeleton className="h-32" />
                  </div>
                </div>
              ))
            : data?.categories.map((cat) => {
                const items = data.features.filter((f) => f.category === cat.id);
                const Icon = ICONS[cat.icon] ?? Tags;
                const meta = CAT_META[cat.id] ?? CAT_META.classification;
                return (
                  <section key={cat.id} className="space-y-4">
                    <div className="flex items-center gap-3">
                      <div className={`flex size-8 items-center justify-center rounded-lg ${meta.bg}`}>
                        <Icon className={`size-4 ${meta.color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h2 className="text-[13px] font-bold text-fg">
                            {meta.emoji} {cat.name}
                          </h2>
                          {cat.id === "email_generation" && (
                            <Badge variant="default">Start here</Badge>
                          )}
                        </div>
                        <p className="text-[11px] text-fg-subtle truncate">{cat.description}</p>
                      </div>
                      <span className="shrink-0 text-[11px] text-fg-subtle">
                        {items.length} feature{items.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {items.map((f) => (
                        <FeatureCard key={f.id} feature={f} catId={cat.id} />
                      ))}
                    </div>
                  </section>
                );
              })}

          {/* Bottom padding */}
          <div className="h-4" />
        </div>
      </ScrollArea>
    </div>
  );
}
