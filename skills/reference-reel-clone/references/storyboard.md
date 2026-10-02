# Stage 1 storyboard (`storyboard.html`)

One self-contained HTML file (images embedded as base64 or saved next to it), readable in a browser. It is the plan the user approves before any money is spent.

**Top**
- Reference link, author, duration, which part is cloned, cut points in seconds.
- Avatar: portrait and character sheet.
- Locks: the FACE / VOICE / NO_TEXT / CAMERA blocks that will go into every clip.

**Timeline and sources** – one row per piece: id (K1, G2 …), what it is, timecodes, duration and the rounded clip length, source:
- `Omni + native voice` – avatar on camera;
- `cloned voice-over` – no avatar on screen;
- `code` – motion graphics;
- `screen recording` – real website or app;
- `Nano Banana Pro` – still plates.

**Visual system**
- Palette picked from the frames (hex values with names).
- Frame grid with coordinates (e.g. 80 px grid on 720×1280).
- Fonts (closest available), weights, tracking; easing and entrance lengths in frames.
- Subtitle styles (e.g. white bold over the creator, translucent plate over graphics).

**Per scene**
- Reference frames at 5 fps around every transition; keyframes in full size.
- Layout: full-frame creator / full-screen graphics / split (what is top, what is bottom).
- Every motion element with in/out timecodes and how it moves.
- Creator text and subtitle chunks with timings (original and clone side by side).
- Notes: what needs a person cut-out, what the screen shows, risks.

**Location plan** – the full location prompt and the plate list.

**Open questions** – decisions only the user can make (hook count, mic, language, outfit). The agent stops here.
