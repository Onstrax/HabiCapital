import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { ink: "#122529", forest: "#123f39", mint: "#d8f5e6", cream: "#f6f7f2", coral: "#eb795e" },
      fontFamily: { sans: ["Arial", "Helvetica", "sans-serif"] },
      boxShadow: { card: "0 16px 45px -30px rgba(16, 52, 45, .34)" },
    },
  },
  plugins: [],
} satisfies Config;
