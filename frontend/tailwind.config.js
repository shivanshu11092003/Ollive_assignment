/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // B&W minimal palette
        zinc: {
          950: '#09090b',
          900: '#18181b',
          850: '#1f1f23',
          800: '#27272a',
          750: '#2e2e32',
          700: '#3f3f46',
          600: '#52525b',
          500: '#71717a',
          400: '#a1a1aa',
          300: '#d4d4d8',
          200: '#e4e4e7',
          100: '#f4f4f5',
          50:  '#fafafa',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'soft':      '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)',
        'elevated':  '0 4px 16px rgba(0,0,0,0.5)',
        'ring':      '0 0 0 2px rgba(255,255,255,0.12)',
        'ring-sm':   '0 0 0 1px rgba(255,255,255,0.08)',
      },
      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          '0%':   { opacity: '0', transform: 'translateX(-8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%':   { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'blink-dot': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.2' },
        },
        'pulse-ring': {
          '0%':   { boxShadow: '0 0 0 0 rgba(255,255,255,0.15)' },
          '100%': { boxShadow: '0 0 0 6px rgba(255,255,255,0)' },
        },
      },
      animation: {
        'fade-in':    'fade-in 0.22s ease both',
        'slide-in':   'slide-in 0.2s ease both',
        'scale-in':   'scale-in 0.18s ease both',
        'shimmer':    'shimmer 2s linear infinite',
        'blink-dot':  'blink-dot 1.4s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 1.4s cubic-bezier(0.4,0,0.6,1) infinite',
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: true,
  }
}
