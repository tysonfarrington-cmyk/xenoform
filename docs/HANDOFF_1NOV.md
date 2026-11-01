# Handoff, Sun 1 Nov 2026

For the next session on Xenoform. The music-video round is finished and pushed. Start from
[MUSIC_VIDEO_PLAN.md](MUSIC_VIDEO_PLAN.md), whose section 8 holds every decision with its reasons.

## Rules

- Commit with `git -c user.name=Owly -c user.email=owly@local commit` and the Co-Authored-By line the app gives you.
  Stage by path, never `git add -A`. Never stash, reset or switch in the shared checkout.
- Push only on Tys's word for that round. His word of 1 Nov covered that round alone.
- Never restart ComfyUI (8188), the proxy (8189) or Tys's desks 47320 and 47321 unless he asks. Check
  `GET http://127.0.0.1:8188/queue` is idle before GPU work.
- No Cloud credits without his word. Never print or paste `COMFY_ORG_API_KEY`.
- Keep objects and clips separate within a Make. In Stems mode this holds within a layer.
- Tys judges by watching: sheets and cuts with full paths. Builders report short summaries, with detail in a README.

## Where it stands

`contest-rc2` is the working branch and `origin/main` follows it. All stages of the plan are in: roles that run, the
pacing engine with Breathe, the taste file, backdrops, assets, the whole song, Stems mode, plus the clips pacing, the
40-clip film pack and the follow-ups. Agent desks 47324 (Tys tests here) and 47325 run the merged tree.

Decided on 1 Nov: Breathe stays off by default; the Vibes control runs from one vibe to all; the taste calls stand as
built; Lead means the lead instrument; the title default is Xenoform; the bundled songs are analysed at 12 fps.

## The analysis rate

Everything but the beats reads at 12 fps, the desk's rate, which the pacing thresholds were tuned at. At 24 the energy
peak reads higher and short drops are lost: ZedsDead v1 finds four at 12 and none at 24. Beats keep a clock of their
own, `analyze.BEAT_FPS` (24), because the tracker can only land on its own frames: at 12 it read Liquid DnB as 90 BPM
for 120 and landed beats 40 to 58 ms off. To raise the rate, first make the drop line independent of it.

Rebuilding at 12 changed Glitch Out's plan: 15 passages for 14, 71 shots for 77 at Breathe, the title at 3:47 for 3:51.
The Glitch Out sheets of 31 Oct and 1 Nov were made on the old 24 fps analysis, so they show the old plan; the ZedsDead
sheets were made at 12. The planner's tests read frozen copies of the old analyses in `tests/fixtures/analyses`, and
`tests/test_songs.py` covers the shipped ones. `examples/demo_features.json` stays at 24, as many tests pin it.

## Waiting on Tys

- Comfy Cloud refused the last morph of the 1 Nov song with HTTP 429, which the code reads as an inactive subscription.
  Check the account before any further Cloud run.
- Tys's desks 47320 and 47321 run older code until he says to restart them.
- Eleven builder worktrees remain under `xenoform-judge-test/.claude/worktrees`, about 14 GB, all merged. They hold raw
  Draft job folders. Remove them on his word.

## Known limits

- Stems: Generate here and Dream are off on a layer. Edit in Resolve exports the composite as one picture.
- A clips song is one Make: one look for the song, and no Cloud path, since Cloud Final morphs library objects only.
- The whole-noun test lets near-repeats through (dragon and origami dragon). At Vibes 1 a vibe's objects repeat.
- Breathe holds one object family per passage, not one place, and the camera orbit follows the cut's Chaos.
- Handoff kinds run at 21 percent at the default Chaos, against the montage's 36.
- `tests/test_turbo.py::test_demo_animatic_is_the_fast_path` is a timing test and can fail on a loaded machine.
- `work/ui/film_pack_v1` holds the old 24-clip pack. Jobs 0935c309 and 1d376198 name its paths.
