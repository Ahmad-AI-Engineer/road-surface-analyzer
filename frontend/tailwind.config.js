/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          900: '#07090f',
          800: '#0b0f17',
          700: '#121826',
          600: '#1b2333',
          500: '#2a3448',
        },
        accent: {
          DEFAULT: '#38bdf8',
          soft: '#7dd3fc',
        },
        hazard: {
          pothole: '#ef4444',
          crack: '#f1c40f',
          alligator: '#9b5cb0',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 40px -10px rgba(56, 189, 248, 0.45)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};
