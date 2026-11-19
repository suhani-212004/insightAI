import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe6fe", 500: "#3b6cf6", 600: "#2a55e0", 700: "#2244b5" },
      },
    },
  },
  plugins: [],
} satisfies Config;
