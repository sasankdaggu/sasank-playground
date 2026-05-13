"use client";

import Link from "next/link";
import { X, Sparkles } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";

const DISMISSED_KEY = "wand_onboarding_banner_dismissed";

const STEPS = ["goals", "skin", "shelf", "agents", "auth"] as const;
const TOTAL = STEPS.length;

function getProgress(onboarding_step: string | null): { pct: number; stepsDone: number } {
  if (!onboarding_step) return { pct: 0, stepsDone: 0 };
  const idx = STEPS.indexOf(onboarding_step as (typeof STEPS)[number]);
  const stepsDone = idx < 0 ? 0 : idx;
  return { pct: Math.round((stepsDone / TOTAL) * 100), stepsDone };
}

export default function OnboardingBanner() {
  const { user, loading } = useAuth();
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(DISMISSED_KEY) === "1";
  });

  if (loading || !user || user.onboarding_step === "complete" || dismissed) return null;

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
  };

  const isResume = !!user.onboarding_step && user.onboarding_step !== "complete";
  const { pct, stepsDone } = getProgress(user.onboarding_step);

  return (
    <div className="w-full bg-gradient-to-r from-pink-50 to-purple-50 border-b border-pink-100">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-4">
        {/* Icon + text */}
        <Sparkles size={16} className="text-[#e85d9b] flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm text-gray-700">
              {isResume
                ? "Resume your shelf setup"
                : "Set up your personalised skincare shelf"}
            </span>
            <span className="text-xs font-semibold text-[#e85d9b] ml-3 flex-shrink-0">
              {stepsDone}/{TOTAL} steps · {pct}%
            </span>
          </div>
          {/* Progress bar */}
          <div className="h-1.5 bg-pink-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-[#e85d9b] rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* CTA + dismiss */}
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          <Link
            href="/onboarding"
            className="text-xs font-semibold bg-[#e85d9b] text-white px-3 py-1.5 rounded-lg hover:bg-pink-600 transition-colors whitespace-nowrap"
          >
            {isResume ? "Resume" : "Start setup"}
          </Link>
          <button onClick={handleDismiss} className="text-gray-400 hover:text-gray-600 p-1">
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
