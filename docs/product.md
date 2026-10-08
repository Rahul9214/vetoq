# Product definition and boundaries

**VETOQ — Trust the Goal. Verify the Action.**

Selected challenge: ET AI Hackathon: Agentic Edition, presented by Accenture; Problem Statement 2, Agentic Cybersecurity — Prompt Injection Firewall.

## Status vocabulary

- Implemented: behavior present in source and supported by verification.
- Planned: approved direction, not a runtime capability.
- Target: desired measurable outcome, not an achieved result.
- Deferred: intentionally absent from the current module.

Module 001 implements engineering foundations only. No security protection, autonomous business action, model access, or F3/D3 capability is currently implemented.

## Product thesis (planned)

VETOQ protects integrated agent execution: content → reasoning context → observable plan/proposal → tool invocation → side effect. The question is both whether content is suspicious and whether an action stays within what the user actually authorized. AI output is evidence, not authority. Models may classify, interpret, correlate, explain, and propose. Deterministic code owns privileged authorization.

Initial audience: teams deploying support-triage agents; initial operator: a person who authorizes one review and one scoped ticket. A later buyer hypothesis is the owner of enterprise agent automation. Buyer demand and business impact have not been measured.

VETOQ owns ingress validation, provenance, analysis evidence, authorization envelopes, guarded dispatch, review integrity, and audit. Downstream agents own business interpretation and proposals. Target applications own their business state, permissions, and receipts. Human operators own delegation, review, credentials, policies, and Git lifecycle.

VETOQ does not promise universal prompt-injection detection, protect bypassing tools, secure an entire operating system, provide a complete SIEM/DLP, or prove arbitrary natural-language intent. The first slice uses a reviewable support-triage permission template. A local reference ticket store is a real target application, not a third-party integration.

## Organizer definitions

The owner verified these definitions against the detailed organizer Problem Statement PDF and supplied them on 7 October 2026. The PDF itself is not stored here; this is an attributed transcription, not independent document verification.

| Level | Definition                                                                           |
| ----- | ------------------------------------------------------------------------------------ |
| F1    | Detect at least 2 attack types                                                       |
| F2    | Detect at least 5 attack types                                                       |
| F3    | Detect at least 7 attack types                                                       |
| D1    | Mostly structured/textual input; acceptable output in a majority of situations       |
| D2    | Mostly structured/textual input with a high degree of demonstrable reliability       |
| D3    | Highly heterogeneous multimodal input with a high degree of demonstrable reliability |

VETOQ targets all nine official families: Instruction Override; Role Change; Secret Extraction; Tool Abuse; Credential Theft; Context Poisoning; Multi-Step Jailbreaks; Encoded Instructions; Indirect Prompt Injection.

F3/D3 remain evidence-dependent targets. Module 002 starts with text; later separately approved modules must expand toward the heterogeneous input requirements. Planned channels include direct messages, documents, webpages, PDF, DOCX, email, Markdown, HTML, API/tool responses, source code, OCR, and text in images. Unsupported formats must never be called inspected or safe.

## Delivery constraints

Official deadline: **11 October 2026, 11:59 PM IST**. Internal freeze: **11 October 2026, 8:00 PM IST**. Leave the remaining time for contingency and submission. Do not substitute a one-day-earlier freeze.

Public event sources: https://economictimes.indiatimes.com/et-spotlight/accenture-ai-hackathon and https://api.unstop.com/hackathons/crp-et-ai-hackathon-agentic-edition-presented-by-accenture-economic-times-1744885 . The detailed PDF governs the supplied F/D definitions.

## Judging and evidence (planned)

Goal-bound enforcement supports relevance, innovation, and robustness. Contextual investigation supports effective AI use. Safe continuation and verified tickets support agentic capability and business value. Provenance/review supports responsible AI. Accessible responsive flows support usability. Reproducible evaluation and recovery support execution and scalability. The public six dimensions are relevance, innovation, technical implementation, impact/scalability, presentation/clarity, and business viability.

Every significant capability needs an implementation reference and evidence. No fabricated metrics, screenshots, deployment links, incidents, or tool outcomes. Fixtures belong only in labeled tests/evaluations. Operational metrics exclude evaluation runs.

Submission artifacts: working accessible prototype, public owner-managed repository, honest README, architecture, pitch deck, 2–4 minute demo, reproducible setup and actual evaluation reports. No artifact currently demonstrates product protection.
