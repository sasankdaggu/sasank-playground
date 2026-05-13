"use client";

import { useState } from "react";
import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import type { Theme } from "@/lib/themes";

interface GoalsStepProps {
  theme: Theme;
  initialGoals: Record<string, string[]>;
  onNext: (goals: Record<string, string[]>) => void;
}

const FACE_CONCERNS = [
  "Acne & breakouts",
  "Dark spots & hyperpigmentation",
  "Dryness & dehydration",
  "Excess oil & shine",
  "Uneven skin tone",
  "Ageing & fine lines",
  "Sensitivity & redness",
  "Enlarged pores",
  "Dullness & fatigue",
  "Dark circles",
];

const HAIR_CONCERNS = [
  "Hair fall & thinning",
  "Dandruff & scalp buildup",
  "Dryness & frizz",
  "Oily roots",
  "Damage & breakage",
  "Slow growth",
];

const BODY_CONCERNS = [
  "Dryness & rough skin",
  "Body acne & bumps",
  "Stretch marks & scars",
  "Tan & uneven tone",
  "Ingrown hairs",
];

const SECTIONS = [
  { key: "face", label: "Face", emoji: "✨", concerns: FACE_CONCERNS },
  { key: "hair", label: "Hair", emoji: "💆", concerns: HAIR_CONCERNS },
  { key: "body", label: "Body", emoji: "🫧", concerns: BODY_CONCERNS },
];

export default function GoalsStep({ theme, initialGoals, onNext }: GoalsStepProps) {
  const [selected, setSelected] = useState<Record<string, Set<string>>>(() => {
    const init: Record<string, Set<string>> = {};
    for (const s of SECTIONS) {
      init[s.key] = new Set(initialGoals[s.key] || []);
    }
    return init;
  });
  const [otherText, setOtherText] = useState<Record<string, string>>({});

  const toggle = (section: string, concern: string) => {
    setSelected((prev) => {
      const next = { ...prev, [section]: new Set(prev[section]) };
      if (next[section].has(concern)) next[section].delete(concern);
      else next[section].add(concern);
      return next;
    });
  };

  const handleNext = () => {
    const goals: Record<string, string[]> = {};
    for (const s of SECTIONS) {
      const arr = Array.from(selected[s.key]);
      const other = otherText[s.key]?.trim();
      if (other) arr.push(other);
      if (arr.length > 0) goals[s.key] = arr;
    }
    onNext(goals);
  };

  const totalSelected = Object.values(selected).reduce((acc, s) => acc + s.size, 0);

  return (
    <div className="flex flex-col gap-8 max-w-xl mx-auto">
      <div className="text-center">
        <div className="text-4xl mb-3">🎯</div>
        <h2 className="text-2xl font-bold mb-2">What are your skin goals?</h2>
        <p className="text-sm opacity-70">Select everything that concerns you — we'll build your routine around these.</p>
      </div>

      {SECTIONS.map((section) => (
        <div key={section.key}>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">{section.emoji}</span>
            <h3 className="font-semibold text-base">{section.label}</h3>
          </div>
          <div className="flex flex-wrap gap-2 mb-2">
            {section.concerns.map((concern) => {
              const active = selected[section.key].has(concern);
              return (
                <button
                  key={concern}
                  onClick={() => toggle(section.key, concern)}
                  className={clsx(
                    "text-xs px-3 py-1.5 rounded-full border transition-all font-medium",
                    active
                      ? "text-white border-transparent"
                      : "bg-white/60 border-gray-200 hover:border-gray-400"
                  )}
                  style={active ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor } : {}}
                >
                  {concern}
                </button>
              );
            })}
          </div>
          <input
            type="text"
            placeholder={`Other ${section.label.toLowerCase()} concern (optional)`}
            value={otherText[section.key] || ""}
            onChange={(e) => setOtherText((prev) => ({ ...prev, [section.key]: e.target.value }))}
            className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 bg-white/60 focus:outline-none focus:border-gray-400 placeholder:text-gray-400"
          />
        </div>
      ))}

      <button
        onClick={handleNext}
        className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm mt-2 transition-all"
        style={{
          backgroundColor: theme.accentColor,
          color: theme.textOnAccent,
        }}
      >
        {totalSelected === 0 ? "Skip for now" : `Continue with ${totalSelected} goals`}
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
