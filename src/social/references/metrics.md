# Metric definitions and interpretation

All metrics describe one explicit platform, selected cohort and capture time.

- **Views/comments**: sum, arithmetic mean, median over observed numeric values; show known N and missing N. If all are missing, summary values are null, not zero. A partial sum is not a complete-account total.
- **Comment rate (CR)**: `100 × comments / views` for a row with known comments and positive views. Zero comments on positive views = 0%. Missing comments/views or zero views = undefined/null.
- **Mean/median CR**: unweighted mean/median of valid per-video rates.
- **Weighted CR**: `100 × Σ comments / Σ views` over the same rows with known comments and positive views. Report pair count and eligible-view coverage. Never divide known comments by all views when comments are missing on some videos.
- **Virality multiplier**: `video views / median known views of the exact selected cohort`. Keep the baseline unrounded for calculation; show enough decimals (e.g. 2,753.5, not 2,754) to reproduce it. It is a relative-view multiple, not share rate, virality probability, or a prediction.
- **Group virality**: median of per-video multiples against the same global cohort baseline; never silently replace the baseline per pattern/month. Group means are available separately.
- **Undefined baseline**: null or zero median → null multiples. Do not divide by zero or invent a fallback baseline without a separately labeled analysis.
- **No sums of CR or virality**: those sums have no useful business meaning.
- **Engagement** (optional): specify the included counters. Only calculate a complete formula when every included counter is present on the row. Never label missing Instagram shares/saves as zero and compare it to TikTok's full engagement.

## Monthly view

Group cumulative counters by UTC **publication month**. Show videos N, views/comments sum/mean/median, mean/median and weighted CR, median multiplier. Unknown dates stay in an unknown bucket. Explain that first/last sample months may be truncated and newer videos have had less time to accumulate views. This is not monthly audience growth, views earned per month, or historical follower change.

For hook comparisons, inspect within-month slices where each formula has enough observations. Equal-age performance needs repeated snapshots or analytics, not simply dividing lifetime views by age. If text and visual always co-occur, their independent effects are not identifiable.

## Pattern evidence

Preserve every selected ID. Count all cohort rows in annotation coverage, including missing covers. Unknown/partial labels are explicit. Single example = hypothesis; 2 = exploratory pair; 3+ = repeated observation. None of these establishes causality or out-of-sample reliability.

Report median, mean, n, top-one view share, and peak versus typical examples. Do not rank a one-video category as a proven winner over a repeated category. A top result can be interesting without being repeatable. Recent underperformance alone does not prove fatigue; comments alone do not prove leads, sales or positive sentiment. Avoid “highest converting” unless actual conversion data was obtained.
