# Lessons from the originating workflow

These are design reasons and regression targets, not a reusable taxonomy.

| Observed issue | Improvement |
| --- | --- |
| Full pagination and hundreds of reply calls before providing insight | Bounded default; selected reply threads; report from existing data on request |
| Interrupting a thread pool left queued work running | Sequential requests with signal-aware shutdown and cache checkpoint after each completed page |
| 2,061 roots were described as if the rest of the counter must be replies | Root/reply identity is based only on observed fields; mismatched counters stay unexplained |
| Collected rows / displayed count was called coverage | Counter comparison is approximate; completeness and representativeness are separate |
| Broad regex classified brand mentions as availability and “need” as praise | Semantic model-authored labels; deterministic validation and counting only |
| Over half the rows were “other”, including clear access requests | Inspect leftovers and report unreviewed rows separately |
| Frequency hid the huge amplification of a small advertising-trust group | Report frequency and likes as different dimensions; do not count likes as people |
| Suggestions were written as if the user owned the competitor Herbi | Read the actual project and tie actions to its product and audience |
| Automatic sentiment mislabeled obvious concerns | No inferred sentiment field by default; require evidence for any optional sentiment analysis |
| Long IDs rendered in scientific notation; dangerous text needed escaping | Namespaced text IDs, reversible CSV escaping, lossless JSON and round-trip checks |
| Spreadsheet dependency discovery/rendering delayed a plain CSV task | Portable stdlib CSV export with meaningful automated checks |
| Instagram behavior was initially assumed to mirror TikTok | Verified adapters, null preservation and explicit reply-cost handling |
| Draft report overclaimed “demand confirmed” | Separate interest from purchases and propose measurable tests |

Public package tests contain invented comments only. Real usernames, response pages,
product reports, credentials and machine-specific paths do not belong in this repo.
