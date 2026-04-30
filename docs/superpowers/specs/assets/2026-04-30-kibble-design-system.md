---
name: Deep Botanical
colors:
  surface: '#f2fcf7'
  surface-dim: '#d3dcd8'
  surface-bright: '#f2fcf7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#ecf6f1'
  surface-container: '#e6f0eb'
  surface-container-high: '#e1eae6'
  surface-container-highest: '#dbe5e0'
  on-surface: '#151d1b'
  on-surface-variant: '#404945'
  inverse-surface: '#29322f'
  inverse-on-surface: '#e9f3ee'
  outline: '#707975'
  outline-variant: '#bfc9c4'
  surface-tint: '#2f6858'
  primary: '#003a2e'
  on-primary: '#ffffff'
  primary-container: '#155243'
  on-primary-container: '#8ac4b0'
  inverse-primary: '#98d2bf'
  secondary: '#58605c'
  on-secondary: '#ffffff'
  secondary-container: '#dae2dc'
  on-secondary-container: '#5c6460'
  tertiary: '#323331'
  on-tertiary: '#ffffff'
  tertiary-container: '#494947'
  on-tertiary-container: '#b9b8b5'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b3efda'
  primary-fixed-dim: '#98d2bf'
  on-primary-fixed: '#002018'
  on-primary-fixed-variant: '#125041'
  secondary-fixed: '#dce4df'
  secondary-fixed-dim: '#c0c8c3'
  on-secondary-fixed: '#161d1a'
  on-secondary-fixed-variant: '#414944'
  tertiary-fixed: '#e4e2df'
  tertiary-fixed-dim: '#c8c6c4'
  on-tertiary-fixed: '#1b1c1a'
  on-tertiary-fixed-variant: '#474745'
  background: '#f2fcf7'
  on-background: '#151d1b'
  surface-variant: '#dbe5e0'
typography:
  h1:
    fontFamily: Noto Serif
    fontSize: 48px
    fontWeight: '400'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  h2:
    fontFamily: Noto Serif
    fontSize: 32px
    fontWeight: '400'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  h3:
    fontFamily: Noto Serif
    fontSize: 24px
    fontWeight: '400'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-sm:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1.0'
    letterSpacing: 0.08em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  container-padding: 40px
  gutter: 24px
  stack-sm: 16px
  stack-md: 32px
  stack-lg: 64px
---

## Brand & Style

The design system is rooted in the quiet luxury of premium tea culture. It evokes feelings of serenity, organic quality, and slow living. The target audience values craftsmanship, sustainability, and editorial-level aesthetics.

The design style is a blend of **Minimalism** and **Tactile Modernism**. It relies on expansive negative space and a restricted, nature-inspired palette to create an immersive, calm environment. Visual noise is eliminated to allow the richness of the forest green and the elegance of the serif typography to lead the experience.

## Colors

The palette is an intentional study in botanical depth.
- **Primary Forest (#155243):** Used for primary navigation, footers, and immersive header sections. It provides the grounding "earth" of the interface.
- **Secondary Sage (#E8F0EA):** Used for container backgrounds, cards, and subtle accents. It acts as a bridge between the dark forest green and the bright cream.
- **Warm Cream (#FCFAF7):** The canvas color for main content areas and high-contrast text backgrounds, providing a softer, more organic feel than pure white.
- **Deep Charcoal Neutral (#2D3633):** Reserved for body text on light backgrounds to maintain readability while staying within the green-tinted spectrum.

## Typography

This design system utilizes a classic editorial pairing to establish hierarchy. **Noto Serif** is used for all headlines to convey a sense of heritage and premium quality. It should be typeset with generous leading and occasional slight negative letter-spacing for large titles.

**Manrope** serves as the functional counterpart. It provides a clean, balanced, and modern reading experience for body copy and UI labels. Its geometric yet friendly proportions prevent the design from feeling too "antique," keeping the interface firmly in a contemporary lifestyle space.

## Layout & Spacing

The layout philosophy follows a **Fixed Grid** model for desktop to ensure an editorial, "packaged" feel, while transitioning to a fluid model for mobile.

A 12-column grid is used with wide gutters (24px) to allow content to breathe. Spacing follows an 8px rhythmic scale, but emphasizes larger increments (32px, 64px) between sections to maintain the minimalist, airy aesthetic characteristic of high-end lifestyle brands. Vertical rhythm should prioritize white space over density.

## Elevation & Depth

Depth is achieved through **Tonal Layers** rather than traditional shadows. The design system avoids heavy drop shadows to maintain its minimalist profile.

1.  **Base Layer:** Warm Cream (#FCFAF7).
2.  **Card Layer:** Sage Green (#E8F0EA) with no shadow, or a very subtle, highly diffused 10% opacity Forest Green shadow for interactivity.
3.  **Immersive Layer:** Forest Green (#155243) used for full-width sections to create a sense of containment.

When depth is required for overlays or modals, a soft backdrop blur (12px) is applied to the layer beneath to mimic the translucency of vellum paper.

## Shapes

The shape language is defined by **Rounded** geometry (0.5rem base), creating an organic and approachable feel. This softness mimics the curved edges of premium tea canisters and natural leaves.

- **Small Components (Buttons, Tags):** 0.5rem (8px) corner radius.
- **Medium Components (Cards, Modals):** 1rem (16px) corner radius.
- **Large Components (Hero Sections):** 1.5rem (24px) corner radius for inner corners.

## Components

- **Buttons:** Primary buttons use a solid Forest Green background with Cream text. Secondary buttons use a Forest Green outline with a 1px stroke. All buttons feature the "Rounded" corner radius and generous horizontal padding.
- **Cards:** Backgrounds are strictly Sage Green (#E8F0EA). Content within cards should have ample internal padding (minimum 24px) to maintain the minimalist feel.
- **Inputs:** Minimalist bottom-border-only or soft-filled Sage Green boxes. Focus states are indicated by a shift to a Forest Green stroke.
- **Chips/Labels:** Small, all-caps Manrope text inside Cream or Sage pills. These should have a pill-shaped (full-radius) finish to distinguish them from actionable buttons.
- **Lists:** Separated by thin, low-opacity Forest Green lines (10% opacity) or simple whitespace.
- **Lifestyle Imagery:** Photography should be integrated with soft-cornered masks, featuring natural lighting and botanical subjects to reinforce the "Deep Botanical" theme.
