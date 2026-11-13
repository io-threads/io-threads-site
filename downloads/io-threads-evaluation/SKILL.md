---
name: io-threads-evaluation
description: Scope an independent check of an AI, hardware or compute claim the way io threads does. Use when someone needs to know whether a claim holds up, which check it needs, or how to write the verdict and its limits.
---

# io threads evaluation method (free version)

Use this to turn "is this number true?" into a scoped check with an honest verdict. It is the method behind io threads' services, not a certification.

## 1. Pin down the claim

- Quote the claim exactly, with where it is published and which version it is about.
- Name who is relying on it (a buyer, a board, a regulator, a launch decision).
- Note any deadline and any data that can't be shared.

If the claim can't be quoted, stop and ask for it. A vague claim can't be checked.

## 2. Pick the check

| If the claim is about… | Start with |
|---|---|
| Anything, and you're not sure what's needed | Diagnostic (one claim, 1–2 weeks) |
| An accuracy or quality number shown to buyers | Eval audit |
| An agent that calls tools or touches customer data | AI security assessment |
| A launch with no agreed definition of "ready" | Launch gating |
| Quality checked by hand as volume grows | Production pipeline |
| Self-hosting or data that can't leave a jurisdiction | Sovereign deployment |
| An agent in production that nobody watches | Agent ops |
| Needing an agent built with its evaluations | Agent build |
| Evaluation being nobody's job | Fractional head of evaluation |
| A report that is more than a year old | Annual re-check |
| Sensors, firmware or device-to-cloud security | Connected hardware check |
| Quantum or photonic fidelity, speed-up or cost claims | Quantum and photonic check |
| GPU spend growing faster than usage | GPU execution cost management |
| AI in hiring, performance or pay decisions | HCM systems check |

## 3. Run the checks you can, and write down the ones you can't

- Prefer evidence the claimant never saw (held-out data, fresh samples).
- Include adversarial cases: misspellings, edge inputs, planted instructions, role escapes.
- Check the checker first: if the judge or scorer is degraded, the run fails; if it has no history, the run abstains.

## 4. Give one of three verdicts

- **PASS**: every check that ran was satisfied.
- **FAIL**: at least one check that ran was broken.
- **ABSTAIN**: not enough ran to say. This is a real answer, never a quiet pass.

Always report **coverage**: which checks ran, as a share of those that applied. Name the ones that didn't run; never drop them.

## 5. Write it up

1. Cover note: what was checked, in one paragraph.
2. The claim, quoted, with source and version.
3. Scope: in and out, side by side.
4. Method and verdict rules.
5. Findings: each value with how it was produced, then a plain reading.
6. Not checked: each gap by name, and what it would take.
7. Next step: scoped, with no obligation.
8. Limits: not a certification, not legal advice.

End with a one-line **board read**: what a decision-maker should do now.

## Limits of this free version

This skill gives the method, not the independence. A check you run on your own claim is still self-checked. For an independent verdict, contact team@io-threads.com.
