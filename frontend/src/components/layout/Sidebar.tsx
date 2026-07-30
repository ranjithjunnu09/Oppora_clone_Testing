import { NavLink } from "react-router-dom";
import {
  Activity,
  History,
  LayoutDashboard,
  Mail,
  ScrollText,
  Tags,
  Target,
  type LucideIcon,
} from "lucide-react";
import type { Category, Feature } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const CATEGORY_ICONS: Record<string, LucideIcon> = { Tags, Mail, Target };

const CATEGORY_COLORS: Record<string, string> = {
  classification: "text-[var(--color-info)]",
  email_generation: "text-[var(--color-accent)]",
  lead_scoring: "text-[var(--color-success)]",
};

function NavItem({
  to,
  icon: Icon,
  label,
  end,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-all duration-150",
          isActive
            ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] shadow-sm"
            : "text-fg-muted hover:bg-surface-2 hover:text-fg",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn(
              "size-4 shrink-0 transition-colors",
              isActive ? "text-[var(--color-accent)]" : "text-fg-subtle group-hover:text-fg-muted",
            )}
          />
          {label}
          {isActive && (
            <span className="ml-auto size-1.5 rounded-full bg-[var(--color-accent)] pulse-dot" />
          )}
        </>
      )}
    </NavLink>
  );
}

export function Sidebar({
  categories,
  features,
  isLoading,
}: {
  categories: Category[];
  features: Feature[];
  isLoading: boolean;
}) {
  return (
    <aside
      className="flex flex-col border-r border-[var(--color-border)] bg-surface"
      style={{ width: 232, flexShrink: 0, height: "100%", overflow: "hidden" }}
    >
      {/* ── Logo ── */}
      <div className="flex h-14 items-center gap-3 border-b border-[var(--color-border)] px-4">
        <div className="relative flex size-8 items-center justify-center rounded-lg bg-[var(--color-accent)] shadow-lg accent-glow">
          <Activity className="size-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold leading-tight text-fg">Oppora AI</p>
          <p className="truncate text-[10px] leading-tight text-fg-subtle">Benchmark Console</p>
        </div>
      </div>

      {/* ── Nav ── */}
      <nav className="space-y-5 overflow-y-auto px-2 py-3" style={{ flex: 1, minHeight: 0 }}>
        {/* Top nav links */}
        <div className="space-y-0.5">
          <NavItem to="/" icon={LayoutDashboard} label="Overview" end />
          <NavItem to="/history" icon={History} label="Run history" />
          <NavItem to="/logs" icon={ScrollText} label="Logs" />
        </div>

        {/* Divider */}
        <div className="px-3">
          <div className="h-px bg-[var(--color-border)]" />
        </div>

        {/* Feature categories */}
        {isLoading
          ? [0, 1, 2].map((i) => (
              <div key={i} className="space-y-2 px-3">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-7 w-full" />
                <Skeleton className="h-7 w-full" />
              </div>
            ))
          : categories.map((cat) => {
              const items = features.filter((f) => f.category === cat.id);
              const Icon = CATEGORY_ICONS[cat.icon] ?? Tags;
              const colorCls = CATEGORY_COLORS[cat.id] ?? "text-fg-subtle";
              return (
                <div key={cat.id} className="space-y-0.5">
                  {/* Category header */}
                  <div className="flex items-center gap-2 px-3 pb-1">
                    <Icon className={cn("size-3 shrink-0", colorCls)} />
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
                      {cat.name}
                    </p>
                    <span className="ml-auto rounded-full bg-surface-2 px-1.5 py-0.5 text-[9px] font-medium tabular-nums text-fg-subtle">
                      {items.length}
                    </span>
                  </div>

                  {/* Feature links */}
                  {items.map((f) => (
                    <NavLink
                      key={f.id}
                      to={`/feature/${f.id}`}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] transition-all duration-100",
                          isActive
                            ? "bg-[var(--color-accent-soft)] font-medium text-[var(--color-accent)]"
                            : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                        )
                      }
                    >
                      <span className="min-w-0 flex-1 truncate">{f.name}</span>
                      {f.is_reasoning_model && (
                        <Badge variant="warning" className="px-1 py-0 text-[9px]">R</Badge>
                      )}
                      {f.call_count !== "1" && (
                        <span className="shrink-0 text-[9px] tabular-nums text-fg-subtle">
                          {f.call_count}×
                        </span>
                      )}
                    </NavLink>
                  ))}
                </div>
              );
            })}
      </nav>

      {/* ── Footer hint ── */}
      <div className="border-t border-[var(--color-border)] px-4 py-3">
        <p className="text-[10px] leading-relaxed text-fg-subtle">
          Prompts are byte-identical to production.
        </p>
      </div>
    </aside>
  );
}
