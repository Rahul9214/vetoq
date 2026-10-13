# Change control

Agents do not silently change the rules below. A human approves the change before implementation. Where the change is material, an accepted ADR accompanies it.

## Changes that require an architecture change request

- The authority invariant
- Goal Lock scope or immutability
- Action Guard decision rules
- Tenancy or non-enumerating access
- Review semantics, including separation of duties
- The tool execution boundary
- A capability ID in the product registry
- Any rule in [SECURITY_INVARIANTS.md](SECURITY_INVARIANTS.md)

## Required contents

| Item              | Requirement                                            |
| ----------------- | ------------------------------------------------------ |
| Rationale         | Why the current rule is insufficient                   |
| Affected contract | The canonical file and section                         |
| Security impact   | What authority, isolation, or evidence changes         |
| Migration impact  | Schema, audit history, and in-flight runs              |
| Alternatives      | What was rejected, including doing nothing             |
| Test impact       | Which denial and recovery tests must change            |
| Human approval    | Explicit approval before code changes the invariant    |
| ADR               | Required when the architecture or an invariant changes |

## Prohibited shortcuts

- Choosing one contract over another when they contradict
- Reinterpreting a capability ID so that PLANNED work counts as IMPLEMENTED
- Rewriting applied migrations
- Weakening a test to preserve a new behavior
- Describing a planned specialist, connector, or deployment as current
- Starting the next roadmap module inside an unrelated change

Routine bug fixes inside an approved module do not need a new ADR when they preserve these rules. The module specification still bounds the work.
