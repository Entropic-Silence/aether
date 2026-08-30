import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "rgb(var(--accent) / <alpha-value>)",
        surface: "var(--surface)",
        sidebar: "var(--sidebar)",
        borderc: "var(--border)",
      },
    },
  },
  plugins: [],
};
export default config;
