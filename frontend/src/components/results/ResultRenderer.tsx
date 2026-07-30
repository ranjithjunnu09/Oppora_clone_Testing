import { useState } from "react";
import { Braces, Check, Copy, Eye, Mail } from "lucide-react";
import type {
  CompanyIndustryResult,
  CompanyLeadsResult,
  EmailSequenceResult,
  LeadTableResult,
  ResultType,
} from "@/lib/types";
import { cn, htmlToText, wordCount } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChainGraph } from "./ChainGraph";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={() => {
        void navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      aria-label="Copy"
    >
      {copied ? <Check className="size-3.5 text-[var(--color-success)]" /> : <Copy className="size-3.5" />}
    </Button>
  );
}

function JsonView({ data }: { data: unknown }) {
  const text = JSON.stringify(data, null, 2);
  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10">
        <CopyButton text={text} />
      </div>
      <pre className="max-h-[32rem] overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 font-mono text-[11px] leading-relaxed text-fg-muted">
        {text}
      </pre>
    </div>
  );
}

/**
 * Renders generated email HTML the way an inbox would, plus the word count.
 * The word count matters: the production prompt demands 50-80 words and
 * "NEVER exceed 125", so it is a cheap, objective way to catch a model that
 * ignores the brief.
 */
function EmailCard({
  subject,
  body,
  meta,
}: {
  subject: string | null;
  body: string;
  meta?: string;
}) {
  const words = wordCount(body);
  const overLimit = words > 125;
  const inSweetSpot = words >= 50 && words <= 80;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-0.5">
            {meta && (
              <p className="text-[10px] uppercase tracking-wider text-fg-subtle">{meta}</p>
            )}
            <p className="truncate text-sm font-semibold text-fg">
              {subject ?? (
                <span className="font-normal italic text-fg-subtle">
                  (same thread, no new subject)
                </span>
              )}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Badge
              variant={overLimit ? "danger" : inSweetSpot ? "success" : "neutral"}
              title="Production prompt targets 50-80 words and forbids exceeding 125"
            >
              {words}w
            </Badge>
            <CopyButton text={htmlToText(body)} />
          </div>
        </div>

        <div
          className="prose-sm max-w-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-[13px] leading-relaxed text-fg-muted [&_p]:mb-2.5 [&_p:last-child]:mb-0"
          dangerouslySetInnerHTML={{ __html: body }}
        />
      </CardContent>
    </Card>
  );
}

function EmailSequenceView({ data }: { data: EmailSequenceResult }) {
  return (
    <div className="space-y-3">
      <EmailCard subject={data.initial.subject} body={data.initial.body} meta="Initial" />
      {data.follow_ups.map((fu, i) => (
        <EmailCard
          key={i}
          subject={fu.subject}
          body={fu.body}
          meta={`Follow-up ${i + 1} · +${fu.days_after} days`}
        />
      ))}
    </div>
  );
}

function LeadTable({ data }: { data: LeadTableResult }) {
  const byId = new Map(data.leads.map((l) => [Number(l.id), l]));
  const scored = [...data.scored_leads].sort(
    (a, b) => a.priority_tier - b.priority_tier || b.score - a.score,
  );
  const excluded = data.leads.filter(
    (l) => !data.scored_leads.some((s) => s.lead_id === Number(l.id)),
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-fg-subtle">
                <th className="px-3 py-2 font-medium">Lead</th>
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 text-right font-medium">Tier</th>
                <th className="px-3 py-2 text-right font-medium">Score</th>
                <th className="px-3 py-2 text-right font-medium">Selected</th>
              </tr>
            </thead>
            <tbody>
              {scored.map((s) => {
                const lead = byId.get(s.lead_id);
                const picked = data.selected.includes(s.lead_id);
                return (
                  <tr
                    key={s.lead_id}
                    className={cn(
                      "border-b border-[var(--color-border)] last:border-0",
                      picked && "bg-[color-mix(in_oklch,var(--color-success)_7%,transparent)]",
                    )}
                  >
                    <td className="px-3 py-2 font-medium text-fg">
                      {String(lead?.name ?? `#${s.lead_id}`)}
                    </td>
                    <td className="px-3 py-2 text-fg-muted">{String(lead?.title ?? "—")}</td>
                    <td className="px-3 py-2 text-fg-subtle">{String(lead?.location ?? "—")}</td>
                    <td className="tnum px-3 py-2 text-right text-fg-muted">{s.priority_tier}</td>
                    <td className="px-3 py-2 text-right">
                      <span className="inline-flex items-center gap-2">
                        <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-border)] sm:block">
                          <span
                            className="block h-full rounded-full bg-[var(--color-accent)]"
                            style={{ width: `${s.score}%` }}
                          />
                        </span>
                        <span className="tnum w-7 text-right font-medium text-fg">{s.score}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {picked && <Badge variant="success">top N</Badge>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {excluded.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-fg-subtle">
            Excluded by the model ({excluded.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {excluded.map((l) => (
              <Badge key={String(l.id)} variant="neutral">
                {String(l.name)} · {String(l.title)}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CompanyLeadsView({ data }: { data: CompanyLeadsResult }) {
  return (
    <div className="space-y-3">
      {data.companies.map((c) => (
        <Card key={c.name}>
          <CardContent className="space-y-2.5 p-4">
            <p className="text-sm font-semibold text-fg">{c.name}</p>
            <div className="space-y-2">
              {c.leads.map((l) => (
                <div
                  key={`${c.name}-${l.id}`}
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-medium text-fg">{l.name}</span>
                    <span className="text-[11px] text-fg-muted">{l.title}</span>
                    <span className="tnum ml-auto text-[10px] text-fg-subtle">#{l.id}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-fg-muted">
                    {l.ai_recommendation}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function CompanyIndustryView({ data }: { data: CompanyIndustryResult }) {
  return (
    <div className="space-y-2">
      {data.map((c, i) => (
        <Card key={i}>
          <CardContent className="flex flex-wrap items-center gap-2 p-3.5">
            <span className="text-sm font-medium text-fg">{c.name}</span>
            <Badge variant="default">{c.industry}</Badge>
            <Badge variant="neutral">{c.approx_employee_size} employees</Badge>
            {c.location && <Badge variant="outline">{c.location}</Badge>}
            {c.domain && (
              <span className="ml-auto font-mono text-[11px] text-fg-subtle">{c.domain}</span>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  Interested: "success",
  "Meeting booked": "success",
  "Meeting completed": "success",
  Won: "success",
  Lead: "info",
  Moderate: "info",
  "Out of office": "warning",
  "Wrong person": "warning",
  "Not interested": "danger",
  Lost: "danger",
  Bounced: "danger",
  Rejected: "danger",
  bounced: "danger",
  rejected: "warning",
};

function StatusBadge({ value }: { value: string }) {
  return (
    <div className="flex items-center justify-center py-8">
      <Badge
        variant={STATUS_VARIANT[value] ?? "neutral"}
        className="px-4 py-1.5 text-sm font-semibold"
      >
        {value}
      </Badge>
    </div>
  );
}

function TextView({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="relative p-4">
        <div className="absolute right-2 top-2">
          <CopyButton text={text} />
        </div>
        <p className="whitespace-pre-wrap pr-10 text-[13px] leading-relaxed text-fg">{text}</p>
      </CardContent>
    </Card>
  );
}

// ── Dispatcher ─────────────────────────────────────────────────────────────

function renderTyped(resultType: ResultType, result: unknown) {
  const r = result as never;
  switch (resultType) {
    case "email_sequence":
      return <EmailSequenceView data={r as EmailSequenceResult} />;
    case "email_single": {
      const d = result as { subject: string; body: string };
      return <EmailCard subject={d.subject} body={d.body} />;
    }
    case "email_list": {
      const d = result as { lead_name: string; emails: string[] };
      return (
        <Card>
          <CardContent className="space-y-2 p-4">
            <p className="text-xs text-fg-muted">{d.lead_name}</p>
            <div className="space-y-1.5">
              {d.emails.map((e, i) => (
                <div
                  key={e}
                  className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2"
                >
                  <Badge variant={i === 0 ? "success" : "neutral"}>#{i + 1}</Badge>
                  <span className="font-mono text-xs text-fg">{e}</span>
                  <span className="ml-auto">
                    <CopyButton text={e} />
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      );
    }
    case "chain":
      return <ChainGraph data={result as never} />;
    case "lead_table":
      return <LeadTable data={result as LeadTableResult} />;
    case "company_leads":
      return <CompanyLeadsView data={result as CompanyLeadsResult} />;
    case "company_industry":
      return <CompanyIndustryView data={result as CompanyIndustryResult} />;
    case "status_badge":
      return <StatusBadge value={String((result as { status: string }).status ?? "—")} />;
    case "text_badge":
      return (
        <div className="flex items-center justify-center py-8">
          <code className="rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface-2)] px-4 py-2 font-mono text-sm text-fg">
            {String((result as { email_pattern: string }).email_pattern ?? "—")}
          </code>
        </div>
      );
    case "text":
      return <TextView text={String((result as { text: string }).text ?? "")} />;
    default:
      return <JsonView data={r} />;
  }
}

export function ResultRenderer({
  resultType,
  result,
}: {
  resultType: ResultType;
  result: unknown;
}) {
  if (result === null || result === undefined) {
    return <p className="py-8 text-center text-xs text-fg-subtle">No result.</p>;
  }

  return (
    <Tabs defaultValue="rendered">
      <TabsList>
        <TabsTrigger value="rendered">
          {resultType.startsWith("email") ? (
            <Mail className="size-3" />
          ) : (
            <Eye className="size-3" />
          )}
          Rendered
        </TabsTrigger>
        <TabsTrigger value="json">
          <Braces className="size-3" />
          Raw JSON
        </TabsTrigger>
      </TabsList>
      <TabsContent value="rendered">{renderTyped(resultType, result)}</TabsContent>
      <TabsContent value="json">
        <JsonView data={result} />
      </TabsContent>
    </Tabs>
  );
}
