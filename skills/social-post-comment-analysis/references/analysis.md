# Analysis contract

## Read context, then code

Read caption/product context and comments before deciding taxonomy. A comment can
both recognize an advertisement and want the product. “Is it free?” is a pricing
question, not necessarily negative sentiment. A store name might indicate geography,
an alternative, a joke or a correction. “Need Android” is an availability request,
not generic praise. Interpret short replies with their parent when available.

Use 5–12 themes when the data supports them; fewer is fine. Define each with
inclusions/exclusions. Separate topic from relevance, actor, sentiment and purchase
intent. Optional sentiment/intent conclusions require semantic evidence, not a
provider's purchase-intent flag or a regex. Product concerns in health, finance and
other sensitive domains are expressed needs, not verified diagnoses or claims.

Choose primary theme by the comment's central point, not an ordered keyword list.
Secondary themes must differ from primary and be unique. The same comment counts
once per mentioned theme. Labels use stable `platform:id`, never array indexes.
All analyzed comments, including social tags and unclear fragments, get a label.
Use a defined social/unclear theme if needed. Keep unseen rows explicitly unreviewed.

## Audit before calculating

Inspect the 20 most-liked audience comments, 20 deterministic/random rows from
across acquisition order, every small/high-impact cluster, and at least 20 “other”
rows (or all if fewer). If substantive missed topics recur, refine and recheck.
Never assume everyone was read just because all IDs have labels. For partial work,
explain the exact selection and use only that subset's denominator.

Keep excluded social/spam/unclear counts visible. Main frequency view: substantive
identified-audience roots. Report replies separately because a few large discussions
can dominate the result. Unknown actors are counted separately and excluded from
the identified-audience denominator until resolved. If creator identification is
incomplete, say so and provide the unknown count rather than implying audience-only
coverage. Optional unique-author statistics need observed account IDs and missing-ID
counts; comments and likes cannot establish the number of distinct potential buyers.

## Product translation

Use the user's project context. Do not prescribe a competitor's architecture or
roadmap for an unrelated product. For a herb/recipe content business, for example,
menu planning may suggest a content/lead-magnet test before a full app rebuild.

Every strong recommendation should have at least one cited example and a frequency
or amplification metric. Distinguish frequent topics from high-like minority topics.
Quote only what supports the conclusion, retain exact source text, and mark
translations. A comment alleging broken recipes supports a perceived-quality issue;
confirm the actual app before calling it an independently verified defect.

Format experiments as: observed friction → proposed change → audience → metric.
Suggested metrics: landing CTA clicks, completed waitlist signups, recipe completion,
trial activation or paid conversion. These are proposed measurements, not results.
Do not declare demand proven, assign precise revenue impact or infer demographics
from usernames or medical conditions from casual remarks.

## CSV

Use stdlib CSV with UTF-8 BOM and normal quoted multiline fields. JSON retains raw
IDs and verbatim text. CSV uses `platform:id` keys to avoid Excel's 15-digit numeric
truncation. Potential formula-like user text gets a leading apostrophe; record
exactly which fields were escaped per row so it can be reversed. Never use `="ID"`.
Check row count, uniqueness and reversible text/ID preservation on readback.
