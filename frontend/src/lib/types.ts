/**
 * Mirrors api/registry.py and api/db.py.
 *
 * These are hand-written rather than generated so the repo has no codegen
 * step. If you add `openapi-typescript` later, point it at
 * http://127.0.0.1:8000/openapi.json and replace this file.
 */

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "select"
  | "json"
  | "code";

export interface FeatureField {
  name: string;
  label: string;
  type: FieldType;
  default: unknown;
  placeholder: string;
  help: string;
  required: boolean;
  options: string[];
  rows: number;
  min: number | null;
  max: number | null;
}

export type ResultType =
  | "company_industry"
  | "text_badge"
  | "status_badge"
  | "email_sequence"
  | "email_single"
  | "email_list"
  | "text"
  | "chain"
  | "company_leads"
  | "lead_table";

export interface Feature {
  id: string;
  name: string;
  category: string;
  source_file: string;
  source_of_truth: string;
  summary: string;
  use_case: string;
  default_model: string;
  result_type: ResultType;
  fields: FeatureField[];
  call_count: string;
  notes: string;
  is_reasoning_model: boolean;
  /** Whether a deterministic rule rubric exists. False reads as "no rubric
   *  yet" in the UI rather than as a score of zero. */
  scoreable: boolean;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export type ProviderId = "anthropic" | "openai";

export interface ProviderStatus {
  id: ProviderId;
  name: string;
  env_key: string;
  configured: boolean;
  notes: string;
}

export interface FeaturesResponse {
  categories: Category[];
  features: Feature[];
  models: string[];
  /** Open-source candidates. No fixed endpoint — set a base URL and pass the
   *  model name your deployment actually serves. */
  open_model_suggestions: string[];
  /** Which provider each preset model routes to, keyed by model name. */
  model_providers: Record<string, ProviderId>;
}

// ── Deterministic quality scoring (api/scoring.py) ─────────────────────────

export type CheckSeverity = "critical" | "major" | "minor";

export interface QualityCheck {
  id: string;
  label: string;
  severity: CheckSeverity;
  passed: boolean;
  detail: string;
  /** Which part of the output failed, e.g. "initial" or "follow_up[1]". */
  scope: string;
  /** The offending text, so the UI can show exactly what tripped the rule. */
  evidence: string[];
  /** The production prompt line this rule comes from. */
  rule_source: string;
}

export interface QualityReport {
  score: number;
  max_score: number;
  scoreable: boolean;
  note: string;
  summary: {
    total: number;
    passed: number;
    failed: number;
    critical: number;
    major: number;
    minor: number;
  };
  checks: QualityCheck[];
}

/** One row per model, repeats collapsed. min/max matter more than the mean for
 *  a migration call — the worst observed run is the one that ships. */
export interface ModelAggregate {
  model: string;
  provider: ProviderId;
  repeats: number;
  completed: number;
  failed: number;
  degraded: number;
  quality_mean: number | null;
  quality_min: number | null;
  quality_max: number | null;
  /** Share of repeats with zero critical rule failures. */
  pass_rate: number | null;
  cost_mean: number;
  cost_max: number;
  latency_mean: number;
  latency_max: number;
  stripped_params: string[];
}

export interface LLMCall {
  index: number;
  label: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
  cost_usd: number;
  cache_hit_rate: number;
  provider: ProviderId;
  /** Params dropped because the routed provider rejects them, e.g. reasoning_effort
   *  on Anthropic's compat layer. Surfaced so a comparison is never silently unfair. */
  stripped_params: string[];
  messages: { role: string; content: string }[];
  response_text: string | null;
  error: string | null;
}

/**
 * "degraded" means the adapter returned a value but at least one underlying
 * LLM call failed — several feature files swallow their own exceptions and
 * return None, so this state keeps those runs from masquerading as passes.
 */
export type RunStatus = "running" | "succeeded" | "degraded" | "failed";

export interface Run {
  id: string;
  feature_id: string;
  model: string;
  base_url: string | null;
  status: RunStatus;
  created_at: number;
  finished_at: number | null;
  inputs: Record<string, unknown>;
  error: string | null;
  call_count: number;
  total_prompt_tokens: number;
  total_cached_tokens: number;
  total_completion_tokens: number;
  total_cost_usd: number;
  total_latency_ms: number;
  batch_id: string | null;
  quality_score: number | null;
  repeat_index: number;
  is_baseline: number;
  /** Only present on single-run and batch fetches, not on history listings. */
  result?: unknown;
  calls?: LLMCall[];
  quality?: QualityReport | null;
}

export interface BatchResponse {
  batch_id: string;
  runs: Run[];
  settled: boolean;
  by_model: ModelAggregate[];
  /** The pinned reference run for this feature, if one is set. */
  baseline: Run | null;
}

export interface RunHandle {
  batch_id: string;
  run_ids: string[];
}

export interface Health {
  status: string;
  providers: ProviderStatus[];
  openai_key_configured: boolean;
  anthropic_key_configured: boolean;
  default_base_url: string;
  feature_count: number;
}

export interface Stats {
  total_runs: number;
  total_cost_usd: number;
  total_calls: number;
  total_tokens: number;
}

// ── Result payload shapes, per Feature["result_type"] ──────────────────────

export interface EmailSequenceResult {
  initial: { subject: string; body: string };
  follow_ups: { subject: string | null; body: string; days_after: number }[];
}

export interface ChainResult {
  intent: string;
  intent_confidence: number;
  should_include_attachments: boolean;
  selected_attachments: number[];
  draft: string;
  guardrail: { guardrail_passed: boolean; issues: string[]; pii_detected: boolean };
  referred_contacts: { email: string; name: string; role: string }[];
  send_decision: { should_send: boolean; confidence: number; reasoning: string } | null;
  final_decision: string;
}

export interface ScoredLead {
  lead_id: number;
  score: number;
  priority_tier: number;
}

export interface LeadTableResult {
  scored_leads: ScoredLead[];
  selected: number[];
  leads: Record<string, unknown>[];
  prompt_preview: string | null;
}

export interface CompanyLeadsResult {
  companies: {
    name: string;
    leads: { id: number; name: string; title: string; ai_recommendation: string }[];
  }[];
}

export interface CompanyIndustryResult
  extends Array<{
    name: string;
    domain: string | null;
    website: string | null;
    industry: string;
    approx_employee_size: string;
    linkedin: string;
    location: string | null;
  }> {}
