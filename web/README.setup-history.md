# Frontend work starts after the backend works

Use Next.js App Router and TypeScript. Before implementing the UI or installing its libraries, ask the user for the exact UI library choices and agree the screen/state brief. No frontend package or design system is selected in this setup.

The planned static export is served by FastAPI on the same origin. Uploads, job polling and results use the existing public API. Never include private job data, evidence images or API keys in the build.
