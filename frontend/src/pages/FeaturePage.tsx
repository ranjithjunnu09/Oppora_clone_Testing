import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  FileCode2,
  Info,
  Loader2,
  Play,
  RotateCcw,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Feature } from "@/lib/types";
import { useAppStore } from "@/store/useAppStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty";
import { ResizableSplit } from "@/components/ui/resizable-split";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { FieldRenderer } from "@/components/features/FieldRenderer";
import { ModelPicker } from "@/components/features/ModelPicker";
import { RunPanel } from "@/components/features/RunPanel";

/* ── Category descriptions for non-technical users ── */
const CATEGORY_GUIDE: Record<string, { what: string; why: string; color: string }> = {
  classification: {
    what: "🏷️ Classification",
    why: "Reads data and labels it automatically — no manual tagging needed.",
    color: "var(--color-info)",
  },
  email_generation: {
    what: "✉️ Email Generation",
    why: "Writes outreach emails, follow-up sequences, and replies automatically.",
    color: "var(--color-accent)",
  },
  lead_scoring: {
    what: "🎯 Lead Scoring",
    why: "Ranks leads by fit so your team focuses on the best prospects first.",
    color: "var(--color-success)",
  },
};

const HOW_TO_STEPS = [
  { n: "1", text: "Fill in the form fields below with sample data." },
  { n: "2", text: "Choose which Claude model to test (claude-sonnet-5 is a good default)." },
  { n: "3", text: "Click Run — results appear on the right within seconds." },
  { n: "4", text: "Compare token count, latency, and cost across models side-by-side." },
];

function defaultsFor(feature: Feature): Record<string, unknown> {
  return Object.fromEntries(feature.fields.map((f) => [f.name, f.default]));
}

/* ═══════════════════════════════════════════════════════════════════
   LEFT PANE — Inputs
   ═══════════════════════════════════════════════════════════════ */
function InputsPane({
  feature,
  data,
  inputs,
  onInputChange,
  onRun,
  onReset,
  isPending,
  missing,
}: {
  feature: Feature;
  data: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.features>>>>["data"];
  inputs: Record<string, unknown>;
  onInputChange: (v: Record<string, unknown>) => void;
  onRun: () => void;
  onReset: () => void;
  isPending: boolean;
  missing: Feature["fields"];
}) {
  const [showGuide, setShowGuide] = useState(false);
  const guide = CATEGORY_GUIDE[feature.category];

  return (
    <div
      className="flex flex-col border-r border-[var(--color-border)] bg-surface"
      style={{ height: "100%", overflow: "hidden", width: "100%" }}
    >
      <ScrollArea style={{ flex: 1, minHeight: 0, width: "100%" }}>
        <div className="space-y-5 p-5" style={{ width: "100%", maxWidth: "100%", overflowX: "hidden", boxSizing: "border-box" }}>

          {/* Feature header */}
          <div className="space-y-2">
            {guide && (
              <div
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                style={{
                  background: `color-mix(in oklch, ${guide.color} 12%, transparent)`,
                  color: guide.color,
                  border: `1px solid color-mix(in oklch, ${guide.color} 25%, transparent)`,
                }}
              >
                {guide.what}
              </div>
            )}
            <div className="flex flex-wrap items-start gap-1.5">
              <h1 className="text-[15px] font-semibold leading-snug text-fg">{feature.name}</h1>
              {feature.is_reasoning_model && <Badge variant="warning">reasoning</Badge>}
              {feature.call_count !== "1" && (
                <Badge variant="info">{feature.call_count} AI calls</Badge>
              )}
            </div>
            <p className="text-xs leading-relaxed text-fg-muted">{feature.summary}</p>
            {feature.use_case && (
              <p className="text-[11px] leading-relaxed text-fg-subtle italic">{feature.use_case}</p>
            )}
          </div>

          {/* Notes banner */}
          {feature.notes && (
            <div className="flex gap-2 rounded-xl border border-[var(--color-warning)]/30 bg-[var(--color-warning-soft)] p-3">
              <Info className="mt-0.5 size-3.5 shrink-0 text-[var(--color-warning)]" />
              <p className="text-[11px] leading-relaxed text-fg-muted">{feature.notes}</p>
            </div>
          )}

          {/* How-to guide */}
          <div className="overflow-hidden rounded-xl border border-[var(--color-border)]">
            <button
              onClick={() => setShowGuide((v) => !v)}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-surface-2"
            >
              <BookOpen className="size-3.5 shrink-0 text-[var(--color-accent)]" />
              <span className="text-[12px] font-medium text-fg">How to use this feature</span>
              <ArrowRight
                className="ml-auto size-3.5 text-fg-subtle transition-transform"
                style={{ transform: showGuide ? "rotate(90deg)" : "none" }}
              />
            </button>
            {showGuide && (
              <div className="fade-in space-y-2.5 border-t border-[var(--color-border)] bg-canvas px-3 py-3">
                {guide && <p className="text-[11px] text-fg-muted">{guide.why}</p>}
                {HOW_TO_STEPS.map((s) => (
                  <div key={s.n} className="flex items-start gap-2.5">
                    <span className="step-badge mt-0.5">{s.n}</span>
                    <p className="text-[11px] leading-relaxed text-fg-muted">{s.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <Separator />

          {/* Model picker */}
          <ModelPicker
            presets={data?.models ?? []}
            modelProviders={data?.model_providers ?? {}}
            openSuggestions={data?.open_model_suggestions ?? []}
          />

          <Separator />

          {/* Input fields */}
          <div className="space-y-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
              Input fields
            </p>
            {feature.fields.map((field) => (
              <FieldRenderer
                key={field.name}
                field={field}
                value={inputs[field.name]}
                onChange={(v) => onInputChange({ ...inputs, [field.name]: v })}
              />
            ))}
          </div>

          {/* Run button */}
          <div className="space-y-2 pt-1">
            <div className="flex gap-2">
              <Button
                className="flex-1"
                disabled={isPending || missing.length > 0}
                onClick={onRun}
              >
                {isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Play className="size-4" />
                )}
                Run
              </Button>
              <Button
                variant="secondary"
                size="icon"
                onClick={onReset}
                aria-label="Reset inputs to defaults"
                title="Reset inputs to defaults"
              >
                <RotateCcw className="size-4" />
              </Button>
            </div>
            {missing.length > 0 && (
              <p className="text-[11px] text-[var(--color-warning)]">
                ⚠ Required: {missing.map((f) => f.label).join(", ")}
              </p>
            )}
          </div>

          <Separator />

          {/* Source file */}
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
              <FileCode2 className="size-3" />
              Source file
            </p>
            <p className="break-all font-mono text-[10px] leading-relaxed text-fg-muted">
              {feature.source_file}
            </p>
            {feature.source_of_truth && (
              <p className="break-all font-mono text-[10px] leading-relaxed text-fg-subtle">
                {feature.source_of_truth}
              </p>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   RIGHT PANE — Results
   ═══════════════════════════════════════════════════════════════ */
function ResultsPane({
  batchId,
  feature,
}: {
  batchId: string | null;
  feature: Feature;
}) {
  return (
    <div style={{ height: "100%", overflow: "hidden" }}>
      <ScrollArea style={{ height: "100%" }}>
        <div className="p-5">
          {batchId ? (
            <RunPanel batchId={batchId} feature={feature} />
          ) : (
            <div
              className="flex flex-col items-center justify-center"
              style={{ minHeight: 440 }}
            >
              <div className="mx-auto w-full max-w-md space-y-4 text-center">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[var(--color-accent-soft)]">
                  <Zap className="size-7 text-[var(--color-accent)]" />
                </div>
                <div>
                  <p className="font-semibold text-fg">Results appear here</p>
                  <p className="mt-1 text-sm text-fg-muted">
                    Fill in the inputs on the left and click{" "}
                    <strong className="text-fg">Run</strong> to test this feature.
                  </p>
                </div>

                {/* Tip */}
                <div className="rounded-xl border border-[var(--color-border)] bg-surface p-4 text-left">
                  <p className="mb-1.5 text-[11px] font-semibold text-fg">💡 Tip</p>
                  <p className="text-[11px] leading-relaxed text-fg-muted">
                    Select multiple models from the <strong className="text-fg">Models</strong>{" "}
                    section to run a <strong className="text-fg">side-by-side comparison</strong>{" "}
                    — you'll see output quality, token count, latency, and cost for each model at once.
                  </p>
                </div>

                {/* What you'll see */}
                <div className="rounded-xl border border-[var(--color-border)] bg-surface p-4 text-left">
                  <p className="mb-2 text-[11px] font-semibold text-fg">📊 What you'll see after running</p>
                  <div className="space-y-1.5">
                    {[
                      "The AI's output for your inputs",
                      "How many tokens were used (= API cost)",
                      "How fast the model responded",
                      "Quality score (if a rubric exists)",
                    ].map((item) => (
                      <div key={item} className="flex items-start gap-2">
                        <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" />
                        <p className="text-[11px] leading-relaxed text-fg-muted">{item}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Drag hint */}
                <p className="flex items-center justify-center gap-1.5 text-[10px] text-fg-subtle">
                  <span>←</span>
                  <span>Drag the handle to resize both panels</span>
                  <span>→</span>
                </p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════════════════════ */
export function FeaturePage() {
  const { featureId = "" } = useParams();
  const queryClient = useQueryClient();
  const { selectedModels, baseUrl, drafts, setDraft, clearDraft, repeats } = useAppStore();
  const [batchId, setBatchId] = useState<string | null>(null);

  const { data } = useQuery({ queryKey: ["features"], queryFn: api.features });
  const feature = useMemo(
    () => data?.features.find((f) => f.id === featureId),
    [data, featureId],
  );

  const inputs = (feature && drafts[featureId]) || (feature ? defaultsFor(feature) : {});

  useEffect(() => setBatchId(null), [featureId]);

  const run = useMutation({
    mutationFn: () =>
      api.run({
        feature_id: featureId,
        inputs,
        models: selectedModels,
        base_url: baseUrl || null,
        repeats,
      }),
    onSuccess: (handle) => {
      setBatchId(handle.batch_id);
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      void queryClient.invalidateQueries({ queryKey: ["history"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!feature) {
    return (
      <div className="p-6">
        <EmptyState
          icon={Info}
          title="Loading feature…"
          description="If this persists, the feature ID in the URL may not exist."
        />
      </div>
    );
  }

  const missing = feature.fields.filter(
    (f) =>
      f.required &&
      (inputs[f.name] === null || inputs[f.name] === undefined || inputs[f.name] === ""),
  );

  return (
    <ResizableSplit
      defaultPct={45}
      minLeft={300}
      maxLeft={750}
      left={
        <InputsPane
          feature={feature}
          data={data}
          inputs={inputs}
          onInputChange={(v) => setDraft(featureId, v)}
          onRun={() => run.mutate()}
          onReset={() => {
            clearDraft(featureId);
            toast.success("Inputs reset to defaults");
          }}
          isPending={run.isPending}
          missing={missing}
        />
      }
      right={<ResultsPane batchId={batchId} feature={feature} />}
    />
  );
}
