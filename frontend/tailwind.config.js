/** Tailwind config for netcensus frontend.
 *  Mirrors the theme that used to live inline in index.html when the CDN
 *  was loaded. Build with: ./tools/tailwindcss -c frontend/tailwind.config.js
 *                                              -i frontend/styles.src.css
 *                                              -o frontend/styles.css --minify
 */
module.exports = {
  content: ["./frontend/index.html"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        mono: ["Fira Code", "Courier New", "monospace"],
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        serif: ["Georgia", "Times New Roman", "serif"],
      },
      colors: {
        surface: {
          DEFAULT: "#111111",
          card: "#1a1a1a",
          alt: "#1c1c1c",
          border: "#262626",
        },
        ink: {
          primary: "#fafafa",
          body: "#b0b0b0",
          muted: "#a3a3a3",
          faint: "#737373",
          quiet: "#525252",
        },
        accent: {
          DEFAULT: "#5eead4",
          pressed: "#4cc9b0",
        },
        alert: "#f87171",
      },
      transitionProperty: { panel: "transform, opacity" },
    },
  },
};
