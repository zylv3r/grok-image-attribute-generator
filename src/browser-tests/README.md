Browser tests use **SIMULATED API responses**. They verify the frontend contract and controls; they do not verify the image provider or backend and never pay for generation.

```bash
npm run build
npm run test:state
npm run test:browser
```

The suite serves the real compiled `dist` through Playwright routes at a simulated origin (`https://atelier.test`), mocks `/api/**`, and writes failure artifacts under `$TMPDIR/atelier-playwright-results`. It opens no listening sockets and never restarts the live Python server. Requires Playwright Chromium (`npx playwright install chromium` if not already installed).

`hardening.spec.ts` preserves immediate arrow-key selection expectations and adds keyboard wrapping, empty Lock/Vary restoration, described checkbox/unset states, global and description searches, 95-value/70-value bounded browsing, exact/approximate preview labels, gallery URL/chip/page behavior, reuse undo, and axe checks at 1440px and 390px. The axe cases use the parent's installed `@axe-core/playwright`; the parent owns saving that development dependency. Accordion tests open attribute headings or collapsed regions before selecting hidden choices.

Capture read-only screenshots against a running real server serving the compiled `dist`:

```bash
STUDIO_BASE_URL=http://127.0.0.1:8123 npm run screenshots
```

Screenshots are saved under `$TMPDIR/atelier-screenshots`. No API interception or generation occurs.

**Parent-only paid generation verification** (not part of the test suite; not run by the frontend worker):

```bash
RUN_PAID_GENERATION=1 STUDIO_BASE_URL=http://127.0.0.1:8123 npm run test:actual
```

This standalone Playwright script uses the rendered UI and real APIs with **no mocks or interception**, previews a composition, submits exactly one paid image job, observes polling, verifies a successful image response and its gallery entry, and captures detail/gallery screenshots plus job JSON under `$TMPDIR/atelier-actual-generation`. It refuses to run without explicit opt-in.

Frontend development uses `npm run dev`; its Vite proxy defaults to the backend at `http://127.0.0.1:8123`. The production bundle uses same-origin API URLs and outputs `dist/index.html` and `dist/assets/`.

If a compatible Chromium executable is already installed, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome` for any browser command. In this worker sandbox, Chromium launch is blocked with `sandbox_host_linux.cc:41 … Operation not permitted`; the browser suite and screenshots therefore require the parent environment. TypeScript and Vite production builds succeed here.

`test:state` runs frontend selection/persistence contract checks against every value in the real `library.json`, with no sockets or provider calls. These pass in the worker sandbox and complement the simulated browser suite.
