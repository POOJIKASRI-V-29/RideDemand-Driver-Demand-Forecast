# RideDemand — frontend

React + Vite + TypeScript dashboard. See the [project README](../README.md) for the
architecture, the API contract and the full setup instructions.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check and bundle into dist/
npm run lint
```

Set `VITE_API_BASE_URL` (see `.env.example`) if the API is not on
`http://localhost:8000`. Vite inlines it at build time, so a change requires a rebuild.

## Structure

| Path | Purpose |
|------|---------|
| `src/App.tsx` | State, data fetching and the loading / empty / ready / error flow |
| `src/components/` | One component per panel of the dashboard |
| `src/services/api.ts` | The only place that talks to the backend |
| `src/types/demand.ts` | Types mirroring the FastAPI response schemas |
| `src/lib/format.ts` | Presentation helpers — formatting only, no prediction logic |
| `src/styles/global.css` | Design tokens and layout |

The frontend performs no prediction, ranking or scoring. Every figure it shows comes from an
API response.
