# Airline Twin — web dashboard

Next.js (App Router) + shadcn/ui + Recharts + react-leaflet front end for the operations simulator.
It talks to the FastAPI backend in `../backend` (default `http://127.0.0.1:8000`, override with
`NEXT_PUBLIC_API_URL`). See the project README, section 3c.

```
npm install
npm run dev            # http://localhost:3000  (webpack + WASM, see postcss.config.mjs)
npm run build
node scripts/final-check.mjs   # end-to-end check: every airline, 3+ simulated days, console errors
node scripts/screenshots.mjs   # dark + light screenshots of every page (uses installed Edge)
```

Simulation, not real flight data. The airlines are fictional; costs are illustrative estimates.
