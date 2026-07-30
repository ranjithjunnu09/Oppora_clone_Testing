import { useState } from "react";
import { AlertTriangle, Check, ChevronRight, Info, X } from "lucide-react";
import type { CheckSeverity, QualityCheck, QualityReport } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const SEVERITY_ORDER: CheckSeverity[] = ["critical", "major", "minor"];

const SEVERITY_STYLE: Record<CheckSeverity, { badge: "danger" | "warning" | "neutral"; label: string }> = {
  critical: { badge: "danger", label: "Critical" },
  major: { badge: "warning", label: "Major" },
  minor: { badge: "neutral", label: "Minor" },
};

function scoreTone(score: number) {
  if (score >= 90) return "text-[var(--color-success)]";
  if (score >= 70) return "text-[var(--color-warning)]";
  return "text-[var(--color-danger)]";
}

function CheckRow({ check }: { check: QualityCheck }) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(check.evidence.length || check.rule_source);

  return (
    <div
      className={cn(
        "rounded-lg border",
        check.passed
          ? "border-[var(--color-border)]"
          : check.severity === "critical"
            ? "border-[var(--color-danger)]"
            : "border-[var(--color-warning)]",
      )}
    >
      <button
        type="button"
        disabled={!expandable}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 px-2.5 py-2 text-left disabled:cursor-default"
      >
        {check.passed ? (
          <Check className="size-3.5 shrink-0 text-[var(--color-success)]" />
        ) : (
          <X
            className={cn(
              "size-3.5 shrink-0",
              check.severity === "critical"
                ? "text-[var(--color-danger)]"
                : "text-[var(--color-warning)]",
            )}
          />
        )}

        <span className={cn("min-w-0 flex-1 truncate text-xs", check.passed ? "text-fg-muted" : "text-fg")}>
          {check.label}
        </span>

        {check.scope && (
          <span className="hidden shrink-0 font-mono text-[10px] text-fg-subtle sm:inline">
            {check.scope}
          </span>
        )}

        {!check.passed && (
          <Badge variant={SEVERITY_STYLE[check.severity].badge} className="shrink-0">
            {SEVERITY_STYLE[check.severity].label}
          </Badge>
        )}

        <span className="hidden max-w-[14rem] shrink-0 truncate text-[11px] text-fg-subtle md:inline">
          {check.detail}
        </span>

        {expandable && (
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-fg-subtle transition-transform",
              open && "rotate-90",
            )}
          />
        )}
      </button>

      {open && (
        <div className="space-y-2 border-t border-[var(--color-border)] px-2.5 py-2">
          <p className="text-[11px] text-fg-muted md:hidden">{check.detail}</p>

          {check.evidence.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
                What tripped it
              </p>
              <div className="flex flex-wrap gap-1">
                {check.evidence.map((e, i) => (
                  <code
                    key={i}
                    className="max-w-full truncate rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-danger)]"
                  >
                    {e}
                  </code>
                ))}
              </div>
            </div>
          )}

          {check.rule_source && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
                Production prompt rule
              </p>
              <p className="font-mono text-[10px] leading-relaxed text-fg-muted">
                {check.rule_source}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Deterministic rule compliance for one run.
 *
 * Every rule is quoted from the production prompt, so a failure here is
 * objectively a failure to follow the brief rather than a matter of taste.
 * The score deliberately does NOT claim the copy is good — see the footer.
 */
export function QualityPanel({ report }: { report: QualityReport }) {
  const [showPassed, setShowPassed] = useState(false);

  if (!report.scoreable) {
    return (
      <Card>
        <CardContent className="flex gap-2 p-3.5">
          <Info className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
          <p className="text-[11px] leading-relaxed text-fg-muted">
            {report.note || "No rule rubric exists for this feature yet."}
          </p>
        </CardContent>
      </Card>
    );
  }

  const failed = report.checks.filter((c) => !c.passed);
  const passed = report.checks.filter((c) => c.passed);
  const sorted = [...failed].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
  );

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 p-4">
          <div className="flex items-baseline gap-1.5">
            <span className={cn("tnum text-3xl font-semibold leading-none", scoreTone(report.score))}>
              {report.score}
            </span>
            <span className="text-xs text-fg-subtle">/ {report.max_score}</span>
          </div>

          <div className="h-8 w-px bg-[var(--color-border)]" />

          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="success">
              {report.summary.passed}/{report.summary.total} rules passed
            </Badge>
            {report.summary.critical > 0 && (
              <Badge variant="danger">
                <AlertTriangle className="size-3" />
                {report.summary.critical} critical
              </Badge>
            )}
            {report.summary.major > 0 && (
              <Badge variant="warning">{report.summary.major} major</Badge>
            )}
            {report.summary.minor > 0 && (
              <Badge variant="neutral">{report.summary.minor} minor</Badge>
            )}
          </div>

          <Tooltip>
            <TooltipTrigger asChild>
              <span className="ml-auto cursor-help text-[10px] text-fg-subtle underline decoration-dotted">
                how is this scored?
              </span>
            </TooltipTrigger>
            <TooltipContent>
              Penalties from 100: critical −25, major −10, minor −3. Rules are taken verbatim from
              the production prompt, so no LLM judge is involved and the score is fully
              reproducible.
            </TooltipContent>
          </Tooltip>
        </CardContent>
      </Card>

      {sorted.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
            Violations ({sorted.length})
          </p>
          {sorted.map((c, i) => (
            <CheckRow key={`${c.id}-${c.scope}-${i}`} check={c} />
          ))}
        </div>
      )}

      {sorted.length === 0 && (
        <Card className="border-[var(--color-success)]">
          <CardContent className="flex items-center gap-2 p-3.5">
            <Check className="size-4 shrink-0 text-[var(--color-success)]" />
            <p className="text-xs text-fg">
              Every rule passed. Note this measures compliance, not whether the copy reads well.
            </p>
          </CardContent>
        </Card>
      )}

      <button
        type="button"
        onClick={() => setShowPassed((v) => !v)}
        className="text-[11px] text-fg-subtle hover:text-fg"
      >
        {showPassed ? "Hide" : "Show"} {passed.length} passing rule
        {passed.length === 1 ? "" : "s"}
      </button>

      {showPassed && (
        <div className="space-y-1.5">
          {passed.map((c, i) => (
            <CheckRow key={`${c.id}-${c.scope}-${i}`} check={c} />
          ))}
        </div>
      )}

      <p className="text-[10px] leading-relaxed text-fg-subtle">
        Rules capture mechanical compliance only. A model can score 100 and still write lifeless
        copy, so a passing score means "did not break the brief" rather than "this is good" — the
        second still needs a human read.
        {report.note && ` ${report.note}`}
      </p>
    </div>
  );
}
