const colors = require('tailwindcss/colors');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // Theme colours, defined per mode in src/index.css
      colors: {
        // The one brand hue, in both themes. Red stays reserved for deleting and errors.
        accent: colors.indigo,
        border: 'rgb(var(--color-border) / <alpha-value>)',
        background: 'rgb(var(--color-background) / <alpha-value>)',
        foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
        muted: {
          foreground: 'rgb(var(--color-muted-foreground) / <alpha-value>)',
        },
      },
      // A light band sweeping over an artwork tile while its image loads
      keyframes: {
        'artwork-shimmer': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'artwork-shimmer': 'artwork-shimmer 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
