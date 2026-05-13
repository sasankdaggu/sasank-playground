"use client";

import { useState } from "react";
import clsx from "clsx";
import { ChevronRight, TrendingDown, FlaskConical, Copy } from "lucide-react";
import type { Theme } from "@/lib/themes";

interface AgentsStepProps {
  theme: Theme;
  onNext: (selectedAgents: string[]) => void;
}

const AGENTS = [
  {
    slug: "price_scout",
    name: "Price Scout",
    icon: TrendingDown,
    emoji: "💰",
    tagline: "Never overpay again",
    description: "Monitors prices across Nykaa, Tira, Purplle and D2C stores. Alerts you when your product drops in price.",
    badge: "Free",
  },
  {
    slug: "ingredient_check",
    name: "Ingredient Check",
    icon: FlaskConical,
    emoji: "🔬",
    tagline: "Know exactly what's in it",
    description: "Flags irritants, allergens, and ingredient clashes based on your skin profile. Full INCI analysis on every product.",
    badge: "Free",
  },
  {
    slug: "dupe_hunter",
    name: "Dupe Hunter",
    icon: Copy,
    emoji: "🕵️",
    tagline: "Same formula, half the price",
    description: "Finds products with nearly identical active ingredients at a lower price. Powered by INCI similarity matching.",
    badge: "Free",
  },
];

export default function AgentsStep({ theme, onNext }: AgentsStepProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set(AGENTS.map((a) => a.slug)));

  const toggle = (slug: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-6 max-w-xl mx-auto">
      <div className="text-center">
        <div className="text-4xl mb-3">🤖</div>
        <h2 className="text-2xl font-bold mb-2">Pick your AI agents</h2>
        <p className="text-sm opacity-70">These work silently in the background on your behalf. All free to start.</p>
      </div>

      <div className="flex flex-col gap-3">
        {AGENTS.map((agent) => {
          const active = selected.has(agent.slug);
          return (
            <button
              key={agent.slug}
              onClick={() => toggle(agent.slug)}
              className={clsx(
                "flex items-start gap-4 p-4 rounded-2xl border transition-all text-left",
                active ? "shadow-md" : "bg-white/60 border-gray-200 opacity-70"
              )}
              style={active ? {
                borderColor: theme.accentColor,
                backgroundColor: `${theme.accentColor}10`,
              } : {}}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-lg"
                style={{ backgroundColor: active ? theme.accentColor : "#f3f4f6" }}
              >
                {agent.emoji}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-semibold text-sm">{agent.name}</span>
                  <span
                    className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                    style={{
                      backgroundColor: active ? theme.accentColor : "#e5e7eb",
                      color: active ? theme.textOnAccent : "#6b7280",
                    }}
                  >
                    {agent.badge}
                  </span>
                </div>
                <div className="text-xs font-medium opacity-70 mb-1">{agent.tagline}</div>
                <div className="text-xs opacity-55 leading-relaxed">{agent.description}</div>
              </div>
              <div
                className="w-5 h-5 rounded-full border-2 flex-shrink-0 mt-0.5 transition-all flex items-center justify-center"
                style={{
                  borderColor: active ? theme.accentColor : "#d1d5db",
                  backgroundColor: active ? theme.accentColor : "transparent",
                }}
              >
                {active && <svg viewBox="0 0 10 8" fill="none" className="w-3 h-2"><path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
              </div>
            </button>
          );
        })}
      </div>

      <button
        onClick={() => onNext(Array.from(selected))}
        className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
        style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
      >
        Activate {selected.size} agent{selected.size !== 1 ? "s" : ""}
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
