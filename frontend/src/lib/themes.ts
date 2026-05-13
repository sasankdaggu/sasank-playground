export interface Theme {
  slug: string;
  name: string;
  emoji: string;
  /** CSS applied to the shelf/onboarding wrapper */
  bg: string;
  shelfColor: string;
  postitColor: string;
  accentColor: string;
  accentHover: string;
  textOnAccent: string;
  borderColor: string;
  slotBorder: string;
  decorations?: string; // extra CSS class(es) for decoration layer
}

export const THEMES: Theme[] = [
  {
    slug: "tile",
    name: "Tile",
    emoji: "🪥",
    bg: "tile-bg",
    shelfColor: "#c8a87a",
    postitColor: "#fff9c4",
    accentColor: "#e85d9b",
    accentHover: "#d14f8a",
    textOnAccent: "#ffffff",
    borderColor: "#e5e7eb",
    slotBorder: "#e85d9b",
  },
  {
    slug: "night",
    name: "Night",
    emoji: "🌙",
    bg: "night-bg",
    shelfColor: "#3d2b1f",
    postitColor: "#1e293b",
    accentColor: "#818cf8",
    accentHover: "#6366f1",
    textOnAccent: "#ffffff",
    borderColor: "#334155",
    slotBorder: "#818cf8",
  },
  {
    slug: "neon",
    name: "Neon Pop",
    emoji: "⚡",
    bg: "neon-bg",
    shelfColor: "#1e0a3c",
    postitColor: "#2d1b4e",
    accentColor: "#f0abfc",
    accentHover: "#e879f9",
    textOnAccent: "#1e0a3c",
    borderColor: "#6b21a8",
    slotBorder: "#f0abfc",
  },
  {
    slug: "retro",
    name: "Retro",
    emoji: "👾",
    bg: "retro-bg",
    shelfColor: "#0f172a",
    postitColor: "#0f172a",
    accentColor: "#22d3ee",
    accentHover: "#06b6d4",
    textOnAccent: "#0f172a",
    borderColor: "#22d3ee",
    slotBorder: "#22d3ee",
  },
  {
    slug: "garden",
    name: "Garden",
    emoji: "🌿",
    bg: "garden-bg",
    shelfColor: "#8b5e3c",
    postitColor: "#d4edda",
    accentColor: "#16a34a",
    accentHover: "#15803d",
    textOnAccent: "#ffffff",
    borderColor: "#bbf7d0",
    slotBorder: "#16a34a",
  },
  {
    slug: "pastel",
    name: "Pastel",
    emoji: "🌸",
    bg: "pastel-bg",
    shelfColor: "#c4b5fd",
    postitColor: "#fce7f3",
    accentColor: "#a855f7",
    accentHover: "#9333ea",
    textOnAccent: "#ffffff",
    borderColor: "#e9d5ff",
    slotBorder: "#a855f7",
  },
];

export const DEFAULT_THEME = THEMES[0];

export function getTheme(slug: string): Theme {
  return THEMES.find((t) => t.slug === slug) ?? DEFAULT_THEME;
}
