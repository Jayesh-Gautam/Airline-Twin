// Tailwind v4 via PostCSS (webpack). This machine's Application Control policy
// blocks native .node binaries, so Tailwind runs its WebAssembly engine
// (NAPI_RS_FORCE_WASI=1 in the npm scripts) and Next.js its WASM compiler.
// The WASM file scanner can't read Windows paths, so tailwind-wasm-sources.mjs
// supplies the class candidates (see that file).
const config = {
  plugins: {
    "./tailwind-wasm-sources.cjs": {},
    "@tailwindcss/postcss": {},
  },
};

export default config;
