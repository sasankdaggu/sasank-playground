"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { THEMES, getTheme, type Theme } from "@/lib/themes";
import { useAuth } from "@/lib/auth-context";
import { getToken } from "@/lib/auth";
import { api } from "@/lib/api";
import GoalsStep from "./components/GoalsStep";
import SkinProfileStep from "./components/SkinProfileStep";
import ShelfBuildStep from "./components/ShelfBuildStep";
import AgentsStep from "./components/AgentsStep";
import AuthStep from "./components/AuthStep";

const STEPS = ["goals", "skin", "shelf", "agents", "auth"] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  goals: "Goals",
  skin: "Skin Profile",
  shelf: "Build Shelf",
  agents: "AI Agents",
  auth: "Save",
};

const STORAGE_KEY = "wand_onboarding_draft";

interface Draft {
  step: Step;
  themeSlug: string;
  goals: Record<string, string[]>;
  skinProfile: Record<string, unknown>;
  selectedAgents: string[];
  shelfProductIds: number[];
}

const DEFAULT_DRAFT: Draft = {
  step: "goals", themeSlug: "tile", goals: {}, skinProfile: {},
  selectedAgents: [], shelfProductIds: [],
};

function loadDraft(): Draft {
  if (typeof window === "undefined") return DEFAULT_DRAFT;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_DRAFT, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return DEFAULT_DRAFT;
}

function saveDraft(draft: Draft) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  } catch { /* ignore */ }
}

function dedupe(ids: number[]): number[] {
  return Array.from(new Set(ids));
}

export default function OnboardingPage() {
  const router = useRouter();
  const { user, updateProfile } = useAuth();
  const [draft, setDraft] = useState<Draft>(() => loadDraft());
  const [theme, setTheme] = useState<Theme>(() => getTheme(loadDraft().themeSlug));
  const [saving, setSaving] = useState(false);

  // If user already completed onboarding, redirect to shelf
  useEffect(() => {
    if (user && user.onboarding_step === "complete") {
      router.replace("/shelf");
    }
    // If user has a saved step, resume from there
    if (user && user.onboarding_step && user.onboarding_step !== "complete") {
      const step = user.onboarding_step as Step;
      if (STEPS.includes(step)) {
        setDraft((prev) => ({ ...prev, step }));
      }
    }
  }, [user, router]);

  const updateDraft = useCallback((updates: Partial<Draft>) => {
    setDraft((prev) => {
      const next = { ...prev, ...updates };
      saveDraft(next);
      return next;
    });
  }, []);

  const handleThemeChange = (slug: string) => {
    setTheme(getTheme(slug));
    updateDraft({ themeSlug: slug });
  };

  const saveStepToBackend = useCallback(async (step: Step) => {
    const token = getToken();
    if (!token) return;
    try {
      await api.auth.updateMe(token, { onboarding_step: step });
    } catch { /* non-critical */ }
  }, []);

  const goToStep = useCallback((step: Step) => {
    updateDraft({ step });
    saveStepToBackend(step);
  }, [updateDraft, saveStepToBackend]);

  const handleGoalsNext = (goals: Record<string, string[]>) => {
    updateDraft({ goals });
    goToStep("skin");
  };

  const handleSkinNext = (skinProfile: Record<string, unknown>) => {
    updateDraft({ skinProfile });
    goToStep("shelf");
  };

  const handleShelfNext = (productIds: number[]) => {
    updateDraft({ shelfProductIds: dedupe(productIds) });
    goToStep("agents");
  };

  const handleAgentsNext = (selectedAgents: string[]) => {
    updateDraft({ selectedAgents });
    goToStep("auth");
  };

  const handleAuthComplete = useCallback(async () => {
    setSaving(true);
    try {
      const token = getToken();

      // 1. Save profile + mark onboarding complete
      await updateProfile({
        theme_slug: draft.themeSlug,
        goals: draft.goals,
        skin_profile: draft.skinProfile,
        selected_agent_slugs: draft.selectedAgents,
        onboarding_step: "complete",
      } as Parameters<typeof updateProfile>[0]);

      // 2. Persist shelf products chosen during onboarding
      if (token && draft.shelfProductIds.length > 0) {
        await Promise.allSettled(
          draft.shelfProductIds.map((id) => api.shelf.add(token, id))
        );
      }

      localStorage.removeItem(STORAGE_KEY);
      router.replace("/shelf");
    } catch {
      setSaving(false);
    }
  }, [draft, updateProfile, router]);

  const currentIndex = STEPS.indexOf(draft.step);

  if (saving) {
    return (
      <div className={clsx("min-h-screen flex items-center justify-center", theme.bg)}>
        <div className="text-center">
          <div className="text-5xl animate-bounce mb-4">✨</div>
          <p className="font-bold text-lg">Building your shelf...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={clsx("min-h-screen transition-all duration-500", theme.bg)}>
      <div className="max-w-2xl mx-auto px-4 py-8">
        {/* Progress */}
        <div className="flex items-center gap-2 mb-10">
          {STEPS.map((step, i) => {
            const done = i < currentIndex;
            const active = i === currentIndex;
            return (
              <div key={step} className="flex items-center gap-2 flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className={clsx(
                      "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all",
                      done ? "text-white" : active ? "text-white ring-2 ring-offset-2" : "opacity-40"
                    )}
                    style={{
                      backgroundColor: done || active ? theme.accentColor : "#d1d5db",
                      outline: active ? `2px solid ${theme.accentColor}` : "none",
                      outlineOffset: 2,
                    }}
                  >
                    {done ? "✓" : i + 1}
                  </div>
                  <span className={clsx("text-xs mt-1 font-medium", active ? "opacity-100" : "opacity-40")}>
                    {STEP_LABELS[step]}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className="h-0.5 flex-1 rounded-full transition-all mb-4"
                    style={{ backgroundColor: done ? theme.accentColor : "#e5e7eb" }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Step content */}
        <div className="transition-all">
          {draft.step === "goals" && (
            <GoalsStep theme={theme} initialGoals={draft.goals} onNext={handleGoalsNext} />
          )}
          {draft.step === "skin" && (
            <SkinProfileStep theme={theme} onNext={handleSkinNext} />
          )}
          {draft.step === "shelf" && (
            <ShelfBuildStep
              theme={theme}
              onThemeChange={handleThemeChange}
              initialProductIds={draft.shelfProductIds}
              onNext={handleShelfNext}
            />
          )}
          {draft.step === "agents" && (
            <AgentsStep theme={theme} onNext={handleAgentsNext} />
          )}
          {draft.step === "auth" && (
            <AuthStep theme={theme} onComplete={handleAuthComplete} />
          )}
        </div>

        {/* Back navigation */}
        {currentIndex > 0 && (
          <button
            onClick={() => goToStep(STEPS[currentIndex - 1])}
            className="mt-8 text-sm opacity-40 hover:opacity-70 block mx-auto"
          >
            ← Back
          </button>
        )}
      </div>
    </div>
  );
}
