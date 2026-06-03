export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cream:       '#FFFDF5',
        foreground:  '#1E293B',
        muted:       '#F1F5F9',
        'muted-fg':  '#64748B',
        accent:      '#7C3AED',
        'accent-fg': '#FFFFFF',
        secondary:   '#F472B6',
        tertiary:    '#FBBF24',
        quaternary:  '#34D399',
        frame:       '#E2E8F0',
        'fluorescent-orange': '#FF6600',
      },
      fontFamily: {
        outfit:  ['Outfit', 'system-ui', 'sans-serif'],
        jakarta: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'pop':          '4px 4px 0px 0px #1E293B',
        'pop-hover':    '6px 6px 0px 0px #1E293B',
        'pop-active':   '2px 2px 0px 0px #1E293B',
        'pop-sm':       '2px 2px 0px 0px #1E293B',
        'pop-lg':       '8px 8px 0px 0px #1E293B',
        'pop-pink':     '8px 8px 0px 0px #F472B6',
        'pop-violet':   '4px 4px 0px 0px #8B5CF6',
        'pop-yellow':   '4px 4px 0px 0px #FBBF24',
        'pop-mint':     '4px 4px 0px 0px #34D399',
      },
      keyframes: {
        wiggle: {
          '0%, 100%': { transform: 'rotate(0deg) scale(1)' },
          '25%':      { transform: 'rotate(-2deg) scale(1.02)' },
          '75%':      { transform: 'rotate(2deg) scale(1.02)' },
        },
        'pop-in': {
          '0%':   { transform: 'scale(0.8)', opacity: '0' },
          '70%':  { transform: 'scale(1.05)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-6px)' },
        },
      },
      animation: {
        wiggle:   'wiggle 0.4s ease-in-out',
        'pop-in': 'pop-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)',
        float:    'float 3s ease-in-out infinite',
      },
      transitionTimingFunction: {
        bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [],
};
