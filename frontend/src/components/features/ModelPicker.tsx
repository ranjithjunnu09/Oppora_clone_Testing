import { useState } from "react";
import { Check, Plus, X } from "lucide-react";
import type { ProviderId } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const PROVIDER_LABEL: Record<ProviderId, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI — production baseline",
};

/**
 * Selecting two or more models turns a run into a comparison: the API creates
 * one run per model under a shared batch id, and they execute in parallel.
 *
 * Models are grouped by provider because that is the axis that matters here —
 * the OpenAI entries are what production runs today, so a Claude result is only
 * meaningful next to one of them.
 */
export function ModelPicker({
  presets,
  modelProviders,
  openSuggestions = [],
}: {
  presets: string[];
  modelProviders: Record<string, ProviderId>;
  openSuggestions?: string[];
}) {
  const { selectedModels, toggleModel, setSelectedModels, repeats, setRepeats } =
    useAppStore();
  const [custom, setCustom] = useState("");
  const [adding, setAdding] = useState(false);

  const customModels = selectedModels.filter((m) => !presets.includes(m));

  const addCustom = () => {
    const name = custom.trim();
    if (name && !selectedModels.includes(name)) {
      setSelectedModels([...selectedModels, name]);
    }
    setCustom("");
    setAdding(false);
  };

  // Preserve the order the API sent (Claude first), then group.
  const groups = (["anthropic", "openai"] as ProviderId[])
    .map((id) => ({ id, models: presets.filter((m) => (modelProviders[m] ?? "openai") === id) }))
    .filter((g) => g.models.length > 0);

  const providersInPlay = new Set(
    selectedModels.map((m) => modelProviders[m] ?? (m.startsWith("claude") ? "anthropic" : "openai")),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-fg-muted">Models</p>
        {selectedModels.length > 1 && (
          <Badge variant="info">{selectedModels.length}-way comparison</Badge>
        )}
      </div>

      {groups.map((g) => (
        <div key={g.id} className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
            {PROVIDER_LABEL[g.id]}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {g.models.map((m) => {
              const active = selectedModels.includes(m);
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleModel(m)}
                  className={cn(
                    "inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] transition-colors",
                    active
                      ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                      : "border-[var(--color-border)] text-fg-muted hover:border-[var(--color-border-strong)] hover:text-fg",
                  )}
                >
                  {active && <Check className="size-3 shrink-0" />}
                  <span className="truncate">{m}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-1.5">
        {customModels.map((m) => (
          <span
            key={m}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-info)] bg-[color-mix(in_oklch,var(--color-info)_15%,transparent)] px-2.5 py-1 font-mono text-[11px] text-[var(--color-info)]"
          >
            {m}
            <button
              type="button"
              onClick={() => toggleModel(m)}
              aria-label={`Remove ${m}`}
              className="hover:opacity-70"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}

        {adding ? (
          <Input
            autoFocus
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") addCustom();
              if (e.key === "Escape") {
                setCustom("");
                setAdding(false);
              }
            }}
            onBlur={addCustom}
            placeholder="claude-… or my-open-model"
            className="h-7 w-52 font-mono text-[11px]"
          />
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="h-[26px] px-2 text-[11px]"
            onClick={() => setAdding(true)}
          >
            <Plus className="size-3" />
            Custom model
          </Button>
        )}
      </div>

      {openSuggestions.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
            Open-source candidates
          </p>
          <div className="flex flex-wrap gap-1.5">
            {openSuggestions.map((m) => {
              const active = selectedModels.includes(m);
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleModel(m)}
                  className={cn(
                    "inline-flex max-w-full items-center gap-1.5 rounded-lg border border-dashed px-2.5 py-1 font-mono text-[11px] transition-colors",
                    active
                      ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                      : "border-[var(--color-border-strong)] text-fg-muted hover:text-fg",
                  )}
                >
                  {active && <Check className="size-3 shrink-0" />}
                  <span className="truncate">{m}</span>
                </button>
              );
            })}
          </div>
          <p className="text-[10px] leading-relaxed text-fg-subtle">
            These have no fixed endpoint. Set a base URL in the header pointing at your own
            deployment, and edit the name to match the model string it actually serves.
          </p>
        </div>
      )}

      <div className="space-y-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="repeats" className="text-xs font-medium text-fg-muted">
            Repeats per model
          </label>
          <div className="flex items-center gap-1.5">
            {[1, 3, 5, 10].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRepeats(n)}
                className={cn(
                  "tnum rounded-md border px-2 py-0.5 text-[11px] transition-colors",
                  repeats === n
                    ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                    : "border-[var(--color-border)] text-fg-muted hover:text-fg",
                )}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
        <p className="text-[10px] leading-relaxed text-fg-subtle">
          {repeats === 1
            ? "A single run tells you almost nothing about an open model — they vary far more run-to-run than frontier ones. Raise this before drawing conclusions."
            : `${repeats} runs per model. Total this batch: ${selectedModels.length * repeats} runs.`}
        </p>
      </div>

      {providersInPlay.has("anthropic") && (
        <p className="text-[10px] leading-relaxed text-fg-subtle">
          Claude runs go through Anthropic's OpenAI-SDK compatibility layer, where{" "}
          <code className="font-mono">strict</code> is ignored — structured output is not
          schema-guaranteed, so an occasional validation failure may be the shim rather than the
          model.
        </p>
      )}

      {customModels.length > 0 && (
        <p className="text-[10px] leading-relaxed text-fg-subtle">
          Names starting with <code className="font-mono">claude</code> route to Anthropic
          automatically; anything else goes to OpenAI unless you set a base URL in the header. Cost
          shows as $0 for models with no price-table entry.
        </p>
      )}
    </div>
  );
}
