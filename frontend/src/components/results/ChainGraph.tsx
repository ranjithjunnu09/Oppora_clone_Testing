import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, CircleSlash, Paperclip, ShieldCheck, UserPlus, X } from "lucide-react";
import type { ChainResult } from "@/lib/types";
import { cn, htmlToText } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

type NodeState = "ok" | "warn" | "skipped";

interface ChainNodeData extends Record<string, unknown> {
  title: string;
  detail: string;
  state: NodeState;
}

const STATE_STYLES: Record<NodeState, string> = {
  ok: "border-[var(--color-success)] bg-[color-mix(in_oklch,var(--color-success)_10%,var(--color-surface))]",
  warn: "border-[var(--color-warning)] bg-[color-mix(in_oklch,var(--color-warning)_10%,var(--color-surface))]",
  skipped: "border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-2)] opacity-60",
};

function ChainNode({ data }: NodeProps<Node<ChainNodeData>>) {
  return (
    <div
      className={cn(
        "w-52 rounded-lg border px-3 py-2 shadow-sm transition-colors",
        STATE_STYLES[data.state],
      )}
    >
      <Handle type="target" position={Position.Left} />
      <p className="text-[11px] font-semibold text-fg">{data.title}</p>
      <p className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-fg-muted">{data.detail}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { chain: ChainNode };

/**
 * Renders the automatic reply agent as the graph it actually is.
 *
 * Node order is the real StateGraph edge order from production, not a guess:
 *   classify_intent -> decide_attachments -> draft_reply -> guardrail_check
 *     -> extract_referred_contacts -> (autonomy? ai_send_decision) -> send|review
 */
export function ChainGraph({ data }: { data: ChainResult }) {
  const { nodes, edges } = useMemo(() => {
    const autonomyRan = data.send_decision !== null;
    const guardrailOk = data.guardrail.guardrail_passed;

    const specs: { id: string; data: ChainNodeData }[] = [
      {
        id: "classify",
        data: {
          title: "1 · classify_intent",
          detail: `${data.intent} (${(data.intent_confidence * 100).toFixed(0)}% confidence)`,
          state: "ok",
        },
      },
      {
        id: "attach",
        data: {
          title: "2 · decide_attachments",
          detail: data.should_include_attachments
            ? `Selected ${data.selected_attachments.join(", ")}`
            : "No attachments included",
          state: data.should_include_attachments ? "ok" : "skipped",
        },
      },
      {
        id: "draft",
        data: {
          title: "3 · draft_reply",
          detail: `${htmlToText(data.draft).slice(0, 70)}…`,
          state: "ok",
        },
      },
      {
        id: "guardrail",
        data: {
          title: "4 · guardrail_check",
          detail: guardrailOk
            ? "Passed, no serious violations"
            : `Failed: ${data.guardrail.issues.join("; ") || "flagged"}`,
          state: guardrailOk ? "ok" : "warn",
        },
      },
      {
        id: "referred",
        data: {
          title: "5 · extract_referred_contacts",
          detail: data.referred_contacts.length
            ? data.referred_contacts.map((c) => c.email).join(", ")
            : "None found",
          state: data.referred_contacts.length ? "ok" : "skipped",
        },
      },
      {
        id: "decide",
        data: {
          title: "6 · ai_send_decision",
          detail: autonomyRan
            ? `${data.send_decision!.should_send ? "SEND" : "DRAFT"} · ${(data.send_decision!.confidence * 100).toFixed(0)}%`
            : "Skipped (autonomy off)",
          state: autonomyRan ? "ok" : "skipped",
        },
      },
      {
        id: "final",
        data: {
          title: data.final_decision === "send" ? "→ Sent" : "→ Human review",
          detail:
            data.final_decision === "send"
              ? "Delivered automatically"
              : "Saved as draft for a human",
          state: data.final_decision === "send" ? "ok" : "warn",
        },
      },
    ];

    const n: Node<ChainNodeData>[] = specs.map((s, i) => ({
      id: s.id,
      type: "chain",
      position: { x: (i % 4) * 240, y: Math.floor(i / 4) * 130 },
      data: s.data,
    }));

    const e: Edge[] = specs.slice(0, -1).map((s, i) => ({
      id: `${s.id}->${specs[i + 1].id}`,
      source: s.id,
      target: specs[i + 1].id,
      animated: false,
      style: { stroke: "var(--color-border-strong)" },
    }));

    return { nodes: n, edges: e };
  }, [data]);

  return (
    <div className="space-y-3">
      <div className="h-[300px] overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--color-border)" />
          <Controls showInteractive={false} className="!border-[var(--color-border)] !bg-surface" />
        </ReactFlow>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardContent className="space-y-2.5 p-4">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-fg">Draft reply</p>
              <Badge variant={data.final_decision === "send" ? "success" : "warning"}>
                {data.final_decision}
              </Badge>
            </div>
            <div
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-[13px] leading-relaxed text-fg-muted"
              dangerouslySetInnerHTML={{ __html: data.draft }}
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-start gap-2">
              <ShieldCheck
                className={cn(
                  "mt-0.5 size-4 shrink-0",
                  data.guardrail.guardrail_passed
                    ? "text-[var(--color-success)]"
                    : "text-[var(--color-danger)]",
                )}
              />
              <div className="min-w-0">
                <p className="text-xs font-medium text-fg">Guardrail</p>
                <p className="text-[11px] text-fg-muted">
                  {data.guardrail.guardrail_passed ? "Passed" : "Failed"}
                  {data.guardrail.pii_detected && " · PII detected"}
                  {data.guardrail.issues.length > 0 && ` · ${data.guardrail.issues.join("; ")}`}
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2">
              <Paperclip className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-fg">Attachments</p>
                <p className="text-[11px] text-fg-muted">
                  {data.should_include_attachments
                    ? `IDs ${data.selected_attachments.join(", ")}`
                    : "None selected"}
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2">
              <UserPlus className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-fg">Referred contacts</p>
                {data.referred_contacts.length ? (
                  <ul className="space-y-0.5">
                    {data.referred_contacts.map((c) => (
                      <li key={c.email} className="text-[11px] text-fg-muted">
                        <span className="font-mono">{c.email}</span>
                        {c.name && ` · ${c.name}`}
                        {c.role && ` (${c.role})`}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[11px] text-fg-muted">None found</p>
                )}
              </div>
            </div>

            <div className="flex items-start gap-2">
              {data.send_decision ? (
                data.send_decision.should_send ? (
                  <Check className="mt-0.5 size-4 shrink-0 text-[var(--color-success)]" />
                ) : (
                  <X className="mt-0.5 size-4 shrink-0 text-[var(--color-warning)]" />
                )
              ) : (
                <CircleSlash className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
              )}
              <div className="min-w-0">
                <p className="text-xs font-medium text-fg">Send decision</p>
                <p className="text-[11px] leading-relaxed text-fg-muted">
                  {data.send_decision
                    ? data.send_decision.reasoning
                    : "Autonomy is off, so this node never ran. Turn it on to add the 6th call."}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
