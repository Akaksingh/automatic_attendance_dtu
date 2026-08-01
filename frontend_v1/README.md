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
screen uses the backend cookie-based JWT authentication API and automatically
sends the CSRF header required for browser mutations.

## Teacher workspace

The teacher dashboard is componentized into a responsive application shell,
group list, roster manager, and attendance session panel. Mobile devices use a
fixed bottom navigation bar; tablet and desktop layouts use a left sidebar.

Teachers can:

- Create and archive groups.
- Add students by roll number.
- Import a roster Excel file asynchronously and poll its import-job progress.
- Remove students from a group.
- Start an attendance session and upload multiple classroom images.
- Watch image-processing progress.
- Review and change each student's present/absent status.
- Finalize or delete a session.

The frontend expects paginated backend responses in the `{ items, meta }`
shape. Excel imports return an import job; the UI polls `/api/import-jobs/{id}`
and exposes the generated row-error CSV when available.

## Production build

```bash
npm run build
```

The build is written to `dist/`. The `backend_v1` Dockerfile builds this
frontend in a Node stage and copies it into the FastAPI image, which serves the
PWA at `/`.

Add future shadcn components with the shadcn CLI; aliases and `components.json`
are already configured. Keep route-level composition in `src/pages`, reusable
feature UI in `src/components`, API calls in `src/lib`, and backend contracts
in `src/types`.
