/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F8FAFC",
        ink: "#0F172A",
        brand: {
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
          950: "#172554",
        },
        gold: {
          50: "#FFFBEB",
          100: "#FEF3C7",
          200: "#FDE68A",
          300: "#FCD34D",
          400: "#FBBF24",
          500: "#D97706",
          600: "#B45309",
          700: "#92400E",
        },
      },
      fontFamily: {
        sans: ["Lato", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["EB Garamond", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        panel: "0 24px 70px -36px rgba(15, 23, 42, 0.28)",
        soft: "0 16px 40px -28px rgba(30, 58, 138, 0.28)",
        inset: "inset 0 1px 0 rgba(255, 255, 255, 0.8)",
      },
      backgroundImage: {
        "legal-shell":
          "radial-gradient(circle at top left, rgba(30, 58, 138, 0.16), transparent 28%), radial-gradient(circle at top right, rgba(180, 83, 9, 0.12), transparent 22%), linear-gradient(180deg, #f8fbff 0%, #f3f7fd 44%, #eef2f8 100%)",
      },
    },
  },
  plugins: [],
};
