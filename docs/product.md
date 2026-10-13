# Product definition and boundaries

**Historical and organizer context.** The canonical product identity, roadmap, and capability registry are [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). This file does not override it.

**VETOQ — Trust the Goal. Verify the Action.**

Historical challenge context: ET AI Hackathon: Agentic Edition, presented by Accenture; Problem Statement 2, Agentic Cybersecurity. That event named the problem space as a prompt-injection firewall. VETOQ is an Agent Execution Security Platform, not that product category.

## Status vocabulary

The capability states IMPLEMENTED, PARTIAL, and PLANNED are defined in [TEST_RELEASE_GATES.md](TEST_RELEASE_GATES.md) and applied only in the registry. The words below are older module language:

- Implemented: behavior present in source and supported by verification.
- Planned: approved direction, not a runtime capability.
- Target: desired measurable outcome, not an achieved result.
- Deferred: intentionally absent from the current module.

Module 001, as of its own completion record, implemented engineering foundations only. Module 002 now implements the text security slice described in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). F3 and D3 are still not achieved.

## Product thesis

The locked path and authority rule are in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) and [SECURITY_INVARIANTS.md](SECURITY_INVARIANTS.md). AI output is evidence, not authority. Models may classify, interpret, correlate, explain, and propose. Deterministic code owns privileged authorization.

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

Historical hackathon deadline: **11 October 2026, 11:59 PM IST**. Historical internal freeze: **11 October 2026, 8:00 PM IST**. Those dates are event history, not the current engineering schedule.

Public event sources: https://economictimes.indiatimes.com/et-spotlight/accenture-ai-hackathon and https://api.unstop.com/hackathons/crp-et-ai-hackathon-agentic-edition-presented-by-accenture-economic-times-1744885 . The detailed PDF governs the supplied F/D definitions.

## Judging and evidence (planned)

Goal-bound enforcement supports relevance, innovation, and robustness. Contextual investigation supports effective AI use. Safe continuation and verified tickets support agentic capability and business value. Provenance/review supports responsible AI. Accessible responsive flows support usability. Reproducible evaluation and recovery support execution and scalability. The public six dimensions are relevance, innovation, technical implementation, impact/scalability, presentation/clarity, and business viability.

Every significant capability needs an implementation reference and evidence. No fabricated metrics, screenshots, deployment links, incidents, or tool outcomes. Fixtures belong only in labeled tests/evaluations. Operational metrics exclude evaluation runs.

Submission artifacts: working accessible prototype, public owner-managed repository, honest README, architecture, pitch deck, 2–4 minute demo, reproducible setup and actual evaluation reports. No artifact currently demonstrates product protection.
