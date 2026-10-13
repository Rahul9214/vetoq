# Design system and release-quality contract

Canonical visual direction and UI truthfulness are [UI_UX_CONTRACT.md](UI_UX_CONTRACT.md). Performance figures below are targets, not measured SLOs. See [OBSERVABILITY_SLO.md](OBSERVABILITY_SLO.md).

## Implemented Module 002 baseline

The responsive product shell includes run submission/recent runs, run detail, provenance/evidence, findings, exact-action review, status, and a ticket outcome that is labeled verified only after read-back. It uses semantic landmarks, a keyboard skip link, visible focus, non-color status text, safe inert source rendering, and reduced-motion CSS. Visible operational labels come from persisted API state.

Canonical tokens live in `apps/web/src/app/globals.css`: paper, ivory, stone, champagne, ink, graphite, lavender, plum, copper, coral, amber, and rose. `apps/web/src/app/vetoq.css` aliases those tokens for existing layout and motion rules. ALLOW, REVIEW, and BLOCK use separate semantic colors and are not the brand palette. Validate each used foreground/background combination.

Use system sans-serif for reading and monospace for technical metadata. No remotely fetched font is required for builds. Fine borders and restrained radii provide separation. Avoid dominant blue, AI gradients, excessive rounded cards, glassmorphism, robots, and decorative graph motion.

## Implemented P0 information architecture

Run submission/recent list; run detail with goal/source/findings/proposal/policy/outcome; inline exact-action review; persisted ticket detail. A dedicated evaluation report view remains deferred. Cross-run analytics, integration management, and graph layouts remain out of scope.

## Responsive acceptance

Validate 320, 360, 390, 430, 768, 1024, 1280, 1440, 1920 CSS px. Use fluid gutters, wrapping Flexbox/Grid, min-width:0, constrained reading widths, and progressive disclosure. No horizontal document overflow, clipped critical actions, unreadable graphs, or oversized modals. Avoid hiding overflow to conceal defects.

Mobile traces use ordered events; graphs have equivalent accessible lists. Tables become structured records when columns no longer fit. Review remains actionable on a small viewport. Wide screens add evidence comparison, not stretched prose.

## Accessibility acceptance

Target WCAG 2.2 AA: semantic landmarks/headings, accessible names, full keyboard use, visible unobscured focus, overlay focus restoration, error recovery, reduced motion, and labels beyond color. Normal text contrast >=4.5:1; large text/non-text controls >=3:1. Primary touch controls target 44px. Reflow at 320 CSS px, 200% text enlargement, and 400% browser zoom must retain functionality.

Automation supplements manual keyboard, assistive-technology, and zoom checks; it does not establish full conformance. The browser suite tests nine widths in Chromium, Firefox, and WebKit, skip-link focus, axe A/AA rules, reduced-motion emulation, and 400% enlarged text at 320px. Record manual validation gaps in handoff.md.

## Performance targets, not measurements

LCP <=2.5s p75, CLS <=0.1, INP <=200ms p75 on a documented representative profile. Read API p95 <=300ms; durable submission p95 <=500ms; in-process policy p95 <=20ms. Text workflow target p95 <=20s excluding human review, provider-dependent. Visible feedback <=200ms and persisted stage updates within two seconds. Initial compressed route JavaScript target <=250KiB. No artificial progress waits. Lazy-load later visualizations and measure actual behavior before claims.
