# Design system and release-quality contract

## Implemented Module 001 baseline

Neutral application shell, semantic header/main/footer, one primary heading, keyboard skip link, visible focus, responsive width/type, dark surfaces, honest foundation-only message, and reduced-motion CSS. There are no product screens, security statuses, charts, or animations.

Tokens live in apps/web/src/app/globals.css. Obsidian #101211, graphite #191d1b, primary ink #e7ece8, muted text #adb7b0, jade #8eddb4, review amber #edbc79, blocked copper #e5a177, critical red #ffaca7. Semantic tokens establish future direction, not actual runtime outcomes. Validate each used foreground/background combination.

Use system sans-serif for reading and monospace for technical metadata. No remotely fetched font is required for builds. Fine borders and restrained radii provide separation. Avoid dominant blue, AI gradients, excessive rounded cards, glassmorphism, robots, and decorative graph motion.

## Planned P0 information architecture

Run submission/list; run detail with goal/source/findings/proposal/policy/outcome; exact-action review; persisted ticket detail. A real evaluation report view is required before submission. Defer cross-run analytics, integration management, and graph layouts. Do not build fake SOC dashboards, generic chatbot landing experiences, or visual policy programming.

## Responsive acceptance

Validate 320, 360, 390, 430, 768, 1024, 1280, 1440, 1920 CSS px. Use fluid gutters, wrapping Flexbox/Grid, min-width:0, constrained reading widths, and progressive disclosure. No horizontal document overflow, clipped critical actions, unreadable graphs, or oversized modals. Avoid hiding overflow to conceal defects.

Mobile traces use ordered events; graphs have equivalent accessible lists. Tables become structured records when columns no longer fit. Review remains actionable on a small viewport. Wide screens add evidence comparison, not stretched prose.

## Accessibility acceptance

Target WCAG 2.2 AA: semantic landmarks/headings, accessible names, full keyboard use, visible unobscured focus, overlay focus restoration, error recovery, reduced motion, and labels beyond color. Normal text contrast >=4.5:1; large text/non-text controls >=3:1. Primary touch controls target 44px. Reflow at 320 CSS px, 200% text enlargement, and 400% browser zoom must retain functionality.

Automation supplements manual keyboard, assistive-technology, and zoom checks; it does not establish full conformance. The foundation browser suite tests nine widths, skip-link focus, axe A/AA rules, reduced-motion emulation, and enlarged text. Record any manual validation gaps in handoff.md.

## Performance targets, not measurements

LCP <=2.5s p75, CLS <=0.1, INP <=200ms p75 on a documented representative profile. Read API p95 <=300ms; durable submission p95 <=500ms; in-process policy p95 <=20ms. Text workflow target p95 <=20s excluding human review, provider-dependent. Visible feedback <=200ms and persisted stage updates within two seconds. Initial compressed route JavaScript target <=250KiB. No artificial progress waits. Lazy-load later visualizations and measure actual behavior before claims.
