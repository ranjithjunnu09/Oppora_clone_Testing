/**
 * ResizableSplit — horizontal split panel with a draggable ↔ handle.
 *
 * - Default: 45% / 55% split.
 * - Drag the grip handle to resize.
 * - Double-click the handle to reset to default split.
 * - Content in either pane is NEVER clipped horizontally — it wraps within the pane width.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface ResizableSplitProps {
  left: React.ReactNode;
  right: React.ReactNode;
  /** Initial left-pane percentage. Default: 45 */
  defaultPct?: number;
  /** Minimum left-pane px */
  minLeft?: number;
  /** Maximum left-pane px */
  maxLeft?: number;
  className?: string;
}

export function ResizableSplit({
  left,
  right,
  defaultPct = 45,
  minLeft = 300,
  maxLeft = 750,
  className,
}: ResizableSplitProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pct, setPct] = useState(defaultPct);
  const isDraggingRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);

  const clampPct = useCallback(
    (containerW: number, raw: number) => {
      const lo = (minLeft / containerW) * 100;
      const hi = (maxLeft / containerW) * 100;
      return Math.max(lo, Math.min(hi, raw));
    },
    [minLeft, maxLeft],
  );

  /* ── Mouse handlers ── */
  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDraggingRef.current || !containerRef.current) return;
      e.preventDefault();
      const rect = containerRef.current.getBoundingClientRect();
      setPct(clampPct(rect.width, ((e.clientX - rect.left) / rect.width) * 100));
    },
    [clampPct],
  );

  const stopDrag = useCallback(() => {
    if (isDraggingRef.current) {
      isDraggingRef.current = false;
      setIsDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
  }, []);

  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    setIsDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", stopDrag);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", stopDrag);
    };
  }, [onMouseMove, stopDrag]);

  /* ── Touch handlers ── */
  const onTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!isDraggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setPct(clampPct(rect.width, ((e.touches[0].clientX - rect.left) / rect.width) * 100));
    },
    [clampPct],
  );

  useEffect(() => {
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", stopDrag);
    return () => {
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", stopDrag);
    };
  }, [onTouchMove, stopDrag]);

  return (
    <div
      ref={containerRef}
      className={cn("flex", className)}
      style={{ height: "100%", overflow: "hidden", position: "relative" }}
    >
      {/* ── Left pane ─────────────────────────────────────────────── */}
      <div
        style={{
          width: `${pct}%`,
          minWidth: minLeft,
          maxWidth: maxLeft,
          flexShrink: 0,
          overflowX: "hidden",
          overflowY: "hidden",
          display: "flex",
          flexDirection: "column",
          boxSizing: "border-box",
        }}
      >
        {left}
      </div>

      {/* ── Drag handle ───────────────────────────────────────────── */}
      <div
        onMouseDown={startDrag}
        onDoubleClick={() => setPct(defaultPct)}
        onTouchStart={(e) => {
          e.preventDefault();
          isDraggingRef.current = true;
          setIsDragging(true);
        }}
        title="Drag to resize · Double-click to reset 50/50"
        className="group relative z-10 flex shrink-0 select-none items-center justify-center"
        style={{ width: 18, cursor: "col-resize" }}
      >
        {/* Thin vertical line */}
        <div
          className={cn(
            "absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors duration-150",
            isDragging
              ? "bg-[var(--color-accent)]"
              : "bg-[var(--color-border)] group-hover:bg-[var(--color-accent)]/50",
          )}
        />

        {/* Grip pill */}
        <div
          className={cn(
            "relative z-10 flex flex-col items-center justify-center gap-[3px] rounded-full border px-[3px] py-3 transition-all duration-150",
            isDragging
              ? "border-[var(--color-accent)] bg-[var(--color-accent)] shadow-[0_0_14px_var(--color-accent-glow)]"
              : "border-[var(--color-border-strong)] bg-surface group-hover:border-[var(--color-accent)]/50 group-hover:bg-[var(--color-accent-soft)]",
          )}
        >
          {/* 6 grip dots in 2 columns */}
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className={cn(
                "size-[3px] rounded-full transition-colors",
                isDragging
                  ? "bg-white"
                  : "bg-[var(--color-border-strong)] group-hover:bg-[var(--color-accent)]",
              )}
            />
          ))}
        </div>

        {/* ← → arrows on hover */}
        <div
          className={cn(
            "absolute inset-y-0 flex items-center justify-center gap-0.5 text-[10px] font-bold text-[var(--color-accent)] opacity-0 transition-opacity duration-150",
            "group-hover:opacity-100",
            isDragging && "opacity-0",
          )}
          style={{ top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
        >
        </div>
      </div>

      {/* ── Right pane ────────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          overflowX: "hidden",
          overflowY: "hidden",
          boxSizing: "border-box",
        }}
      >
        {right}
      </div>

      {/* ── Global drag capture overlay ───────────────────────────── */}
      {isDragging && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            cursor: "col-resize",
          }}
        />
      )}
    </div>
  );
}
