# After round 1 of the Songline redesign (T5, branch t5-strip)

The desk's five steps after the strip round (docs/notes/t5-strip.md), on a desk running the branch at
127.0.0.1:47354, at 1440x900 and at 375x812 (the phone). The before pictures are in [../shots](../shots/).

Rerun (desk must be up with the bundled songs and cut 31680167, Glitch Out 30 s, in My videos):

    set NODE_PATH=C:\Projects\xf-uiaudit\node_modules
    node docs\ui_review\tools\capture_after.js [baseUrl]

Writes the jpegs here and manifest.json (url, viewport, note, page and console errors per shot); about 95 s. It never
presses Render Draft, Re-cut, Queue, Grow or any other GPU button.

| Shot | What it shows | Before |
|---|---|---|
| 01_source | No song: the strip ghosted, the bundled songs with the demo by name, My videos, Choose a song as the one action | 01, 03 |
| 02_plan_first_screen, 02_plan | Glitch Out with the first vibe: the sketch monitor (no GPU), the vibe rail, the strip with the 13 planned shots in the Draft window round the main drop, one estimate | 04, 06 |
| 02b_plan_dock | Shot 5 clicked: the object it lands on docks under the strip, in song time, bar and beat | 11 |
| 03_tweak | The Feel row, the four knobs (the Chaos knob under the pointer fills the hint line), the rows with cost tags, the Project panel | 12, 13 |
| 04c_render_progress_simulated | **Simulated** in the desk's client state (no job ran): Morph 6 of 13, shots 1 to 5 solid, 6 pulsing, 7 to 13 hatched, the clock and Stop in the step bar | 60 to 60e |
| 04_render | Cut 31680167 reopened from #render/31680167: the player, the cut's shots on the song at 2:08, Quality and Render the whole song | 40, 61 |
| 04b_render_inspector | Shot 5 clicked: the inspector under the strip, its head "2:19 in the song, bar 53 beat 1 · 0:11 in the cut" | 42 to 42d |
| 05_perform | The Perform card that opens /vj with the cut | 50 |
| *_375_screen | The phone screen as each step opens: one column, the strip as the section overview under the monitor, the step bar stuck to the bottom | 29, 46 |
| *_375 | The same steps as full pages | 29, 46 |

Notes:

- A full-page capture keeps the layout viewport, so the sticky step bar would be drawn mid-page over other things; for
  those shots the script scrolls to the top and draws the bar where the page ends. The viewport shots show it where
  it sits on screen.
- 04b is a viewport shot because a second full-page capture of the same page paints the strip's own scroller at 0:00
  while the page keeps its place (the DOM reads 13 shots in view): a Chromium quirk, not the desk.
- The phone has no 02b or 04b: at phone width the strip is the overview, with no shots to click.
- The only console error is /favicon.ico (404), as in the review.
