# Test and release gates

A module is not complete because its unit tests passed. Capability status words in this file are the only meanings used by the registry in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Capability states

| State       | Meaning                                                                                        |
| ----------- | ---------------------------------------------------------------------------------------------- |
| IMPLEMENTED | The repository runtime and its tests demonstrate the capability as defined in the registry     |
| PARTIAL     | A real subset exists. The rest of the capability is absent. Do not describe the subset as done |
| PLANNED     | Direction only. No runtime behavior may be presented as this capability                        |

Fixtures, mocks, and illustrations are not operational evidence. A live provider call with a tiny denominator is a smoke, not a reliability result.

## Module lifecycle

```text
spec
→ architecture and security review
→ GREEN A
→ implementation
→ focused tests
→ integration and database
→ real runtime proof
→ security, failure, and recovery
→ performance
→ accessibility and responsive behavior
→ full repository verify
→ docs
→ human acceptance
→ GREEN B
→ selective manual Git
→ pull request and CI
→ squash merge
→ sync
→ next module
```

GREEN A authorizes implementation of an approved slice. GREEN B is human acceptance after the gates above. Agents do not merge, tag, or start the next module.

## Evidence required before IMPLEMENTED

- The behavior is in production code, not only in a test double.
- A failing case is tested, not only the happy path.
- Security capabilities include the denial path: wrong workspace, wrong principal, stale review, or failed closed provider, as applicable.
- Database behavior is shown on the disposable test database, not on development data.
- UI status claims are traced to API fields.

PARTIAL is the correct word when only some of that evidence exists.
