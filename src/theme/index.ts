import { Platform, useColorScheme } from 'react-native';

// ─── Farvepaletter ────────────────────────────────────────────────────────────
// Varme neutraler frem for kold hvid/sort — reducerer sensorisk belastning.

export const LightColors = {
  background: '#F8F7F4',    // Varm off-white
  surface: '#FFFFFF',
  surfaceRaised: '#F0EDE8', // Kort, modal
  text: '#1A1714',
  textSecondary: '#6B6560',
  textTertiary: '#A09A95',
  border: '#DDD9D3',
  error: '#DC2626',
  success: '#16A34A',
  warning: '#D97706',
} as const;

export const DarkColors = {
  background: '#100F0D',
  surface: '#1C1A18',
  surfaceRaised: '#272421',
  text: '#F0EDE8',
  textSecondary: '#9C9590',
  textTertiary: '#605B57',
  border: '#2E2B28',
  error: '#F87171',
  success: '#4ADE80',
  warning: '#FCD34D',
} as const;

export type ThemeColors = typeof LightColors;

// ─── Typografi ────────────────────────────────────────────────────────────────

export const Typography = {
  fontFamily: Platform.select({
    ios: 'System',
    android: 'sans-serif',
    default: 'System',
  }),
  size: {
    xs: 12,
    sm: 14,
    base: 16,
    md: 18,
    lg: 22,
    xl: 28,
    xxl: 36,
  },
  weight: {
    regular: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },
  lineHeight: {
    tight: 1.25,
    normal: 1.5,   // God læsbarhed for ADHD
    relaxed: 1.75,
  },
} as const;

// ─── Afstand (4 px-grid) ─────────────────────────────────────────────────────

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

// ─── Hjørner ─────────────────────────────────────────────────────────────────

export const Radius = {
  sm: 8,
  md: 14,
  lg: 22,
  full: 9999,
} as const;

// ─── Minimum touch-target ────────────────────────────────────────────────────
// 48 pt opfylder iOS HIG og WCAG 2.5.5 — vigtigt for ADHD-brugere.

export const TouchTarget = {
  min: 48,
} as const;

// ─── Skygger ─────────────────────────────────────────────────────────────────

export const Shadows = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
} as const;

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Returnerer det rigtige farvesæt baseret på systemets farvetema.
 * Brug denne hook i alle komponenter der skal respektere dark mode.
 */
export function useColors(): ThemeColors {
  const scheme = useColorScheme();
  return scheme === 'dark' ? DarkColors : LightColors;
}
