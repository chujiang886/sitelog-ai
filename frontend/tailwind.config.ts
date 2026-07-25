import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        boip: {
          primary: {
            main: "#2563eb",
            light: "#dbeafe",
            dark: "#1e40af",
          },
          accent: "#14b8a6",
        },
      },
    },
  },
  plugins: [],
};

export default config;
