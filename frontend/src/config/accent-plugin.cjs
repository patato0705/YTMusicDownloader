// The --accent-* variables behind the accent-* colours (@theme in
// src/index.css), loaded there with @plugin
const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');
// The accent colours offered in the appearance menu; the first is the default
const ACCENTS = require('./accents.json');

const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
// How Tailwind writes its palettes: 'oklch(51.1% 0.262 276.966)'
const OKLCH = /^oklch\(([\d.]+)% ([\d.]+) ([\d.]+)\)$/;

for (const name of ACCENTS) {
  if (!SHADES.every((shade) => OKLCH.test(colors[name]?.[shade] ?? ''))) {
    throw new Error(`src/config/accents.json: "${name}" is not a Tailwind colour palette`);
  }
}

/**
 * OKLCH -> linear-light sRGB, where luminance is a weighted sum and colours
 * mix evenly. A wide-gamut shade has channels past 0 or 1: kept, not clipped.
 */
const toLinear = (value) => {
  const [lightness, chroma, hue] = value.match(OKLCH).slice(1).map(Number);
  const L = lightness / 100;
  const a = chroma * Math.cos((hue * Math.PI) / 180);
  const b = chroma * Math.sin((hue * Math.PI) / 180);
  const [l, m, s] = [
    L + 0.3963377774 * a + 0.2158037573 * b,
    L - 0.1055613458 * a - 0.0638541728 * b,
    L - 0.0894841775 * a - 1.291485548 * b,
  ].map((c) => c ** 3);
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
};
const luminance = ([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
/** Linear light as a CSS colour, wide gamut included */
const toCss = (linear) => `color(srgb-linear ${linear.map((c) => Number(c.toFixed(5))).join(' ')})`;

/**
 * One palette's shades as --accent-* variables, each as light as the default
 * accent's shade of the same number: the app's text on and around the accent
 * was tuned on the default, so every accent keeps its contrast (white on 600
 * stays 6.4:1; a bit less on a screen that clips a wide-gamut shade, 6.1:1 for
 * rose). Lighter palettes come out a step or so deeper than Tailwind's.
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
    return [`--accent-${shade}`, toCss(colour)];
  }));
};

// The default accent on the root, and each choice under data-accent. Set on
// <html> it themes the whole app; on a swatch, it shows that swatch's own hue.
module.exports = plugin(({ addBase }) => {
  const [defaultAccent, ...others] = ACCENTS;
  addBase({
    [`:root, [data-accent="${defaultAccent}"]`]: accentVariables(defaultAccent),
    ...Object.fromEntries(others.map((name) => [`[data-accent="${name}"]`, accentVariables(name)])),
  });
});
