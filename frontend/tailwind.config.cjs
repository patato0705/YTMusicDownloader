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
    },
  },
  plugins: [],
}
