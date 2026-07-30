import type {
  BatchResponse,
  FeaturesResponse,
  Health,
  Run,
  RunHandle,
  Stats,
} from "./types";

/** Vite proxies /api to the FastAPI layer on :8000 in dev (see vite.config.ts). */
const BASE = "/api";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the API. Is it running?  uvicorn api.main:app --reload --port 8000",
      0,
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  features: () => request<FeaturesResponse>("/features"),
  stats: () => request<Stats>("/stats"),

  run: (body: {
    feature_id: string;
    inputs: Record<string, unknown>;
    models: string[];
    base_url?: string | null;
    api_key?: string | null;
    repeats?: number;
  }) =>
    request<RunHandle>("/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRun: (runId: string) => request<Run>(`/runs/${runId}`),
  pinBaseline: (runId: string) =>
    request<{ status: string; run_id: string }>(`/runs/${runId}/baseline`, {
      method: "POST",
    }),
  getBatch: (batchId: string) => request<BatchResponse>(`/batch/${batchId}`),
  history: (featureId?: string, limit = 100) =>
    request<{ runs: Run[] }>(
      `/history?limit=${limit}${featureId ? `&feature_id=${featureId}` : ""}`,
    ),
  clearHistory: () => request<{ status: string }>("/history", { method: "DELETE" }),
  logs: (featureId?: string, limit = 200) =>
    request<{ logs: unknown[]; total: number }>(
      `/logs?limit=${limit}${featureId ? `&feature_id=${featureId}` : ""}`,
    ),
};

export { ApiError };
