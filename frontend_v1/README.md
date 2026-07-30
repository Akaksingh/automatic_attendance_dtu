# Frontend v1

React 19, TypeScript, Vite, Tailwind CSS v4, standard shadcn components and
theming, and PWA support for ClassLens — the enhanced attendance application.

## Development

Start `backend_v1` on port 8000, then run:

```bash
npm install
npm run dev
```

Vite serves the app on port 5173 and proxies `/api/*` to FastAPI. The login
screen currently verifies that the FastAPI server is available; real login is
intentionally pending an authentication API.

## Production build

```bash
npm run build
```

The build is written to `dist/`. The `backend_v1` Dockerfile builds this
frontend in a Node stage and copies it into the FastAPI image, which serves the
PWA at `/`.

Add future shadcn components with the shadcn CLI; aliases and `components.json`
are already configured.
