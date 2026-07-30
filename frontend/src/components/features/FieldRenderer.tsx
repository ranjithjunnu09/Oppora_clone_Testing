import { useCallback, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { json as jsonLang } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";
import { AlertCircle } from "lucide-react";
import type { FeatureField } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { InfoHint } from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * JSON editor with live validation.
 *
 * Holds its own text buffer so a half-typed object does not blow away the
 * parent's parsed value; only valid JSON is pushed up.
 */
function JsonField({
  value,
  onChange,
  rows,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  rows: number;
}) {
  const initial = useMemo(() => JSON.stringify(value ?? null, null, 2), []);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  const handle = useCallback(
    (next: string) => {
      setText(next);
      if (!next.trim()) {
        setError(null);
        onChange(null);
        return;
      }
      try {
        onChange(JSON.parse(next));
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Invalid JSON");
      }
    },
    [onChange],
  );

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          "overflow-hidden rounded-lg border transition-colors",
          error ? "border-[var(--color-danger)]" : "border-[var(--color-border)]",
        )}
      >
        <CodeMirror
          value={text}
          height={`${Math.min(rows * 20 + 16, 420)}px`}
          extensions={[jsonLang()]}
          theme={oneDark}
          onChange={handle}
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            highlightActiveLine: false,
            autocompletion: false,
          }}
        />
      </div>
      {error && (
        <p className="flex items-center gap-1.5 text-[11px] text-[var(--color-danger)]">
          <AlertCircle className="size-3 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

export function FieldRenderer({
  field,
  value,
  onChange,
}: {
  field: FeatureField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const control = () => {
    switch (field.type) {
      case "boolean":
        return (
          <div className="flex h-9 items-center">
            <Switch checked={Boolean(value)} onCheckedChange={onChange} />
          </div>
        );

      case "number":
        return (
          <Input
            type="number"
            value={value === null || value === undefined ? "" : String(value)}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
            placeholder={field.placeholder}
          />
        );

      case "select":
        return (
          <Select value={String(value ?? "")} onValueChange={onChange}>
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder || "Select..."} />
            </SelectTrigger>
            <SelectContent>
              {field.options.map((o) => (
                <SelectItem key={o} value={o}>
                  {o}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );

      case "textarea":
        return (
          <Textarea
            value={String(value ?? "")}
            rows={field.rows}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
          />
        );

      case "json":
      case "code":
        return <JsonField value={value} onChange={onChange} rows={field.rows} />;

      default:
        return (
          <Input
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
            className={field.label.startsWith("{") ? "font-mono text-xs" : undefined}
          />
        );
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={field.name}>
          {field.label}
          {field.required && <span className="ml-0.5 text-[var(--color-danger)]">*</span>}
        </Label>
        {field.help && <InfoHint>{field.help}</InfoHint>}
      </div>
      {control()}
    </div>
  );
}
