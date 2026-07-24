# Last-mile Work Ownership

| Work | Owner | Owned scope | Shared-file rule | Dependency | Evidence |
|---|---|---|---|---|---|
| W1 | GPT-5.5 | workflow and processed-message persistence | no GUI changes | none | persistence boundary tests |
| W2 | GPT-5.5 | boxscore worker and importing views | coordinator integrated afterward | W1 contract | four terminal-outcome tests |
| W3 | GPT-5.5 | message date recovery model/view | coordinator integrated afterward | W1 | real-fixture recovery tests |
| W4 | GPT-5.5 + GPT-5.6 Sol integration | season-final result contract and coordinator | `gui/app.py` integrated by primary | W1 | preview/save/rerun tests |
| W5 | GPT-5.6 Sol | reviewer exclusion, completion policy, dashboard pending count | integrated after W1/W3 | W1, W3 | exclusion/change/pending tests |
| W6 | GPT-5.6 Sol | workflow-aware result routing | single owner for `gui/app.py` | W2, W4, W5 | destination/report tests |
| W7 | GPT-5.5 (Sonnet 5 unavailable) | shared typed record editor and wrappers | message-view integration by primary | W3 | editor parity/validation tests |
| W8 | independent GPT-5.5 verifier | tests, CI, evidence review only | no product-code edits | W1-W7 | independent verification report |

Sonnet 5 was attempted first for W3/W7 as directed. Its CLI could not reach the API in this environment, so the bounded implementation work was reassigned to GPT-5.5. The primary agent retained decomposition, shared-interface integration, and final verification.
