/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#d9e5ff',
          500: '#3b6ef5',
          600: '#2856d8',
          700: '#1d43ad',
        },
      },
    },
  },
  plugins: [],
}