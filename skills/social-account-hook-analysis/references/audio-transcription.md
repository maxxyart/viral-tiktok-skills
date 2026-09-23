# Optional audio transcription

Use this only when the user asks for spoken hooks or audio transcripts. The local report works without it. The helper supports the selected TikTok videos or Instagram Reels in `videos.json`, reading media URLs from the saved `raw/page-*.json` responses. It downloads the actual videos from those CDN URLs; it does not transcribe captions and does not call ScrapeCreators again. CDN URLs can expire, so replaying an old feed may produce errors.

Requirements: Python 3.10+, `ffmpeg` on PATH, and `GOOGLE_API_KEY` or `GEMINI_API_KEY` in the environment for live transcription. Do not place keys in arguments, output folders, commits or logs. Gemini model access and prices vary; check the current official pricing/model documentation when quoting a cost. The default model is `gemini-2.5-flash-lite`; use `--model` for another supported model if necessary.

```bash
python3 <skill-dir>/scripts/audio_transcribe.py --out <run-dir> --dry-run
python3 <skill-dir>/scripts/audio_transcribe.py --out <run-dir> --workers 3
# Optional bounded pilot before all selected videos:
python3 <skill-dir>/scripts/audio_transcribe.py --out <run-dir> --limit 3
```

The dry-run is read-only and reports selected rows, rows with saved HTTPS media URLs, known duration and a maximum of two Gemini calls per resolvable video. Inspect coverage and get approval for significant cost if needed. Without `--limit`, every selected video is attempted; failures remain visible. Completed per-video JSON files under `transcripts/` are cached. A rerun uses cached success and fills incomplete results rather than retranscribing them.

Outputs are `transcripts.json`, `audio_usage.json`, cached per-video results, downloaded `video_media/`, extracted `audio_media/`, and sampled `opening_frames/`. The full audio and a separately clipped 0–3-second segment are transcribed independently. `opening_0_3s` comes from the short segment, not from the model's estimate of the opening while hearing the whole clip. Machine ASR can still make mistakes; check important source quotes against the audio. `audio_usage.json` totals tokens in saved successful responses and is not a billing ledger for retries or discarded earlier calls.

If a cover is missing, the helper points `cover_file` at an extracted 0.35-second frame and labels it `opening_frame_fallback`. Regenerate contact sheets with `covers.py --sheets-only`; do not run the regular cover download again after annotation, because it may overwrite the fallback status. Such a frame is opening-frame evidence; a downloaded cover remains cover evidence. Neither alone proves the timing of cuts, actions or on-screen text through the full video.

After visual annotation, run `social.py analyze` and then `hook_report.py` with authored `insights.json`. The renderer joins by selected video ID, includes spoken opening and full audio transcript in every table row, and writes `videos_with_transcripts.csv`. If a video failed transcription, show its status and do not invent speech. The helper does **not** analyze the visual contents of a full video; that is a separate, explicitly requested workflow.
