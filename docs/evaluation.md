# Evaluation methodology — planned, not results

No detector, attack simulation, evaluation corpus, security metric, or achieved F/D level is implemented in Module 001. Foundation test counts are engineering verification, not product efficacy.

## Separate the questions

1. Detection: did the system correctly identify malicious content?
2. Authorization: did it prevent the exact prohibited side effect?
3. Utility: did the legitimate business task complete correctly?
4. Reliability: do those observations hold across variants, repetitions, formats, and failures?

F3 requires at least seven official categories. VETOQ targets all nine listed in product.md. A blocked operation alone does not prove that its attack category was detected. D3 requires heterogeneous multimodal input and demonstrable reliability; text-only success does not qualify.

## Proposed targets and measurement

| Metric                   | Target, not achievement                                          | Measurement                                                                                       |
| ------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Attack recall            | >=95% overall, with per-family reporting                         | Correctly detected malicious episodes / malicious episodes                                        |
| Benign pass              | >=95%                                                            | Benign episodes without unnecessary security interruption / benign episodes                       |
| False-positive rate      | <=5%                                                             | Benign episodes incorrectly flagged; also report unnecessary review and block rates               |
| Unsafe action prevention | Zero unauthorized side effects in regression and live evaluation | Denied prohibited proposals / prohibited proposals; separately count episode-level unsafe effects |
| Task completion          | >=90% benign, >=80% attacked-but-recoverable                     | Verified correct outcomes / applicable tasks                                                      |
| Format coverage          | Every claimed format tested                                      | Adapter × extraction × attack × utility matrix                                                    |
| Attack coverage          | All nine families                                                | Cases, variants, sample size, failures per family                                                 |
| Latency                  | See design-system.md                                             | Stage and end-to-end p50/p95, including configuration                                             |

All actual results: **not measured**.

## Corpus and execution plan

Module 002 smoke target: three distinct cases per family plus twenty benign controls. Submission target: twenty per family plus one hundred benign cases if budget permits. Separate development and held-out attack templates. Include benign quotations/security discussions and both malicious direct messages and content carried through the actual indirect channel. Later formats need extraction and incomplete-processing cases.

Repeat stochastic cases three times where feasible. Record dataset version, application version, policy/prompt/model identifiers, configuration, attempts, latency, denominators, failures, and uncertainty intervals. Do not cherry-pick a successful run. If no prohibited proposal occurred, proposal-level prevention is N/A, not 100%.

Compare content-only, permission-only, combined defense, and isolated unprotected baselines where safe and useful. Unprotected tests use disposable data and restricted tools, never real secrets or arbitrary network egress. Fixtures stay in clearly labeled tests/evaluation runs, separated from operational metrics. Reports contain real observations only.

## D3 evidence gate

Before claiming a format, validate parsing, provenance, limits, adversarial variants, legitimate utility, and reliable failure handling. Text extracted from an image is not proof that all multimodal threats are handled. Record unsupported and incompletely processed content honestly. Map the organizer's exact heterogeneous set before approving expansion modules.

## Submission

README summarizes measured capability and limitations. The live product shows actual runs. The demo tells one causal story. The deck explains buyer value and differentiation. Full reports provide reproducible evidence. No invented business savings, calibrated probabilities, or benchmarks.
