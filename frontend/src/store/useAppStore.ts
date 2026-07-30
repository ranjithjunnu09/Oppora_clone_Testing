import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AppState {
  /** Models selected for the next run. Two or more turns a run into a comparison. */
  selectedModels: string[];
  /** Per-feature draft inputs, so navigating away does not lose a filled form. */
  drafts: Record<string, Record<string, unknown>>;
  /** Self-hosted OpenAI-compatible endpoint. Empty means real OpenAI. */
  baseUrl: string;
  theme: "dark" | "light";
  /** Runs per model. >1 is what makes an open-model comparison trustworthy. */
  repeats: number;

  setSelectedModels: (models: string[]) => void;
  toggleModel: (model: string) => void;
  setDraft: (featureId: string, inputs: Record<string, unknown>) => void;
  clearDraft: (featureId: string) => void;
  setBaseUrl: (url: string) => void;
  setRepeats: (n: number) => void;
  toggleTheme: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Anthropic is the default benchmark target. The gpt-* models remain
      // selectable as the production baseline to compare against.
      selectedModels: ["claude-sonnet-5"],
      drafts: {},
      baseUrl: "",
      theme: "dark",
      repeats: 1,

      setSelectedModels: (models) => set({ selectedModels: models }),

      toggleModel: (model) =>
        set((s) => {
          const has = s.selectedModels.includes(model);
          // Never let the selection fall to zero — a run needs at least one model.
          if (has && s.selectedModels.length === 1) return s;
          return {
            selectedModels: has
              ? s.selectedModels.filter((m) => m !== model)
              : [...s.selectedModels, model],
          };
        }),

      setDraft: (featureId, inputs) =>
        set((s) => ({ drafts: { ...s.drafts, [featureId]: inputs } })),

      clearDraft: (featureId) =>
        set((s) => {
          const next = { ...s.drafts };
          delete next[featureId];
          return { drafts: next };
        }),

      setBaseUrl: (baseUrl) => set({ baseUrl }),

      setRepeats: (repeats) => set({ repeats: Math.max(1, Math.min(20, repeats)) }),

      toggleTheme: () =>
        set((s) => {
          const theme = s.theme === "dark" ? "light" : "dark";
          document.documentElement.classList.toggle("dark", theme === "dark");
          return { theme };
        }),
    }),
    {
      name: "oppora-console",
      // Bumped when the default model set changed from OpenAI to Claude, so
      // existing persisted state does not pin users to the old default.
      version: 2,
      migrate: (persisted, version) => {
        const s = persisted as Partial<AppState> | undefined;
        if (version < 2) {
          return { ...s, selectedModels: ["claude-sonnet-5"] } as AppState;
        }
        return s as AppState;
      },
      // Drafts can get large (the lead-scoring batch default is 200 leads);
      // keep them in memory only, persist just the small settings.
      partialize: (s) => ({
        selectedModels: s.selectedModels,
        baseUrl: s.baseUrl,
        theme: s.theme,
        repeats: s.repeats,
      }),
    },
  ),
);
