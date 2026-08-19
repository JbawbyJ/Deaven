/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'deaven-bg': '#0a0a0a',
        'deaven-surface': '#111111',
        'deaven-border': '#1f1f1f',
        'deaven-gold': '#c9a84c',
        'deaven-fire': '#ef4444',
        'deaven-strong': '#f97316',
        'deaven-watch': '#eab308',
        'deaven-pass': '#6b7280',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        fire: '0 0 24px rgba(239, 68, 68, 0.25), 0 0 2px rgba(239, 68, 68, 0.5)',
      },
      animation: {
        pulseFire: 'pulseFire 2s ease-in-out infinite',
        barGrow: 'barGrow 0.8s ease-out forwards',
      },
      keyframes: {
        pulseFire: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(239, 68, 68, 0.4)' },
          '50%': { boxShadow: '0 0 20px rgba(239, 68, 68, 0.7)' },
        },
        barGrow: {
          from: { width: '0%' },
          to: { width: 'var(--bar-width)' },
        },
      },
    },
  },
  plugins: [],
};
