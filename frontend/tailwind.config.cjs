const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');
// The accent colours offered in the appearance menu; the first is the default
const ACCENTS = require('./src/config/accents.json');

const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

for (const name of ACCENTS) {
  if (!SHADES.every((shade) => /^#[0-9a-f]{6}$/i.test(colors[name]?.[shade] ?? ''))) {
    throw new Error(`src/config/accents.json: "${name}" is not a Tailwind colour palette`);
  }
}

// Colour maths in linear light, where luminance is a weighted sum
const toLinear = (hex) =>
  hex.slice(1).match(/../g).map((pair) => {
    const c = parseInt(pair, 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
const luminance = ([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
/** Linear light -> '99 102 241', the form rgb(var(...) / alpha) takes */
const rgbChannels = (linear) =>
  linear
    .map((c) => Math.round(255 * (c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055)))
    .join(' ');

/**
 * One palette's shades as --accent-* variables, each as light as the default
 * accent's shade of the same number: the app's text on and around the accent
 * was tuned on the default, so every accent keeps its contrast (white on 600
 * stays 6.3:1). Lighter palettes come out a step or so deeper than Tailwind's.
 */
const accentVariables = (name) => {
  const palette = SHADES.map((shade) => toLinear(colors[name][shade]));
  return Object.fromEntries(SHADES.map((shade) => {
    const target = luminance(toLinear(colors[ACCENTS[0]][shade]));
    // The palette's two shades either side of the target, mixed to meet it
    let colour = target >= luminance(palette[0]) ? palette[0] : palette[palette.length - 1];
    for (let i = 0; i < palette.length - 1; i += 1) {
      const [lighter, darker] = [luminance(palette[i]), luminance(palette[i + 1])];
      if (target <= lighter && target >= darker) {
        const t = (lighter - target) / (lighter - darker);
        colour = palette[i].map((c, channel) => c + (palette[i + 1][channel] - c) * t);
        break;
      }
    }
    return [`--accent-${shade}`, rgbChannels(colour)];
  }));
};

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
        // The one brand hue, in both themes, picked by each viewer (ThemeContext).
        // Red stays reserved for deleting and errors.
        accent: Object.fromEntries(
          SHADES.map((shade) => [shade, `rgb(var(--accent-${shade}) / <alpha-value>)`]),
        ),
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
        // A bottom sheet coming up from under the screen's edge
        'sheet-up': {
          '0%': { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        // A menu growing out of its button (useDropdown sets the origin)
        'menu-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'menu-out': {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
      },
      animation: {
        'artwork-shimmer': 'artwork-shimmer 1.6s ease-in-out infinite',
        'sheet-up': 'sheet-up 0.28s cubic-bezier(0.32, 0.72, 0, 1)',
        'fade-in': 'fade-in 0.28s ease-out',
        'menu-in': 'menu-in 0.16s cubic-bezier(0.16, 1, 0.3, 1)',
        // As long as EXIT_MS in useDropdown, and holding its end until the menu goes
        'menu-out': 'menu-out 0.11s ease-in forwards',
      },
    },
  },
  plugins: [
    // The default accent on the root, and each choice under data-accent. Set on
    // <html> it themes the whole app; on a swatch, it shows that swatch's own hue.
    plugin(({ addBase }) => {
      const [defaultAccent, ...others] = ACCENTS;
      addBase({
        [`:root, [data-accent="${defaultAccent}"]`]: accentVariables(defaultAccent),
        ...Object.fromEntries(others.map((name) => [`[data-accent="${name}"]`, accentVariables(name)])),
      });
    }),
  ],
}
