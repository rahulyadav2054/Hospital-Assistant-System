/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef6fb", 100: "#d6e9f5", 500: "#2e6da4", 600: "#245a89", 700: "#1f4e79", 900: "#132f49" },
      },
    },
  },
  plugins: [],
};
