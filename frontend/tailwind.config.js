/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F7FBFF",
        ink: "#0F172A",
        brand: {
          50: "#EEF8FF",
          100: "#D7EEFF",
          200: "#B0DDFF",
          300: "#7BC7FF",
          400: "#44ADF4",
          500: "#178FDB",
          600: "#026DBD",
          700: "#025EA2",
          800: "#0A4D80",
          900: "#103E64",
          950: "#0B2741",
        },
        trust: {
          50: "#EDF9F2",
          100: "#D6F2E1",
          200: "#AFE5C2",
          300: "#7DD59D",
          400: "#45BD70",
          500: "#10A94F",
          600: "#0D9445",
          700: "#0F7739",
          800: "#125E31",
          900: "#124D2D",
        },
      },
      fontFamily: {
        sans: ["Lato", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["EB Garamond", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        panel: "0 26px 78px -40px rgba(2, 51, 94, 0.24)",
        soft: "0 16px 40px -26px rgba(2, 109, 189, 0.24)",
        inset: "inset 0 1px 0 rgba(255, 255, 255, 0.8)",
      },
      backgroundImage: {
        "legal-shell":
          "radial-gradient(circle at top left, rgba(2, 109, 189, 0.16), transparent 30%), radial-gradient(circle at top right, rgba(16, 169, 79, 0.12), transparent 24%), linear-gradient(180deg, #f7fbff 0%, #f1f8f8 46%, #e9f2f5 100%)",
      },
    },
  },
  plugins: [],
};
