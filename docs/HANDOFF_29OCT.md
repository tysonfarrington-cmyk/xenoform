# Handoff, Thu 29 Oct 2026, about 6 am AEDT

For the session that carries the contest entry to the line. Deadline: the Typeform closes Sat 31 Oct 3:00 am AEDT;
Tys's own cut-off is Fri 30 Oct 9 pm AEDT. The app freezes once the audit fixes below are in. Tys pushes, posts and
submits himself; nothing is pushed or posted by an agent.

## Rules (Tys's, verbatim where it matters)

- Commit with `git -c user.name=Owly -c user.email=owly@local commit` and end the message with the Co-Authored-By
  line the app gives you. Never push. Stage only your own files by path, never `git add -A`; this is a shared
  checkout, so never stash, reset or switch branches.
- Never restart ComfyUI (8188), the proxy (8189) or Tys's desks 47320 and 47321 unless he asks in words. Check
  `GET http://127.0.0.1:8188/queue` is idle before any GPU work. The agent desks are 47324 (Tys tests here), 47325
  and 47326 (the recorder); they are started with `COMFY_ORG_API_KEY` copied from the Windows user variable into
  their environment (see "Comfy Cloud" below).
- No spending without a word from Tys: Cloud Final spends Comfy Cloud credits (about 6 a morph); the paid partner
  path stays off. Never print or paste the key.
- Git Bash heredocs here mangle backslashes and apostrophes: write scripts with the Write tool and run them by path.
- Keep clips and objects separate (a Make is Objects or Your clips, never both).

## Where it stands

Commits today, all on `contest-rc2`, none pushed: f712b93 (None vibe, walkthrough script), f9eaa7e (the desk no
longer blinks on a click), c785f31 (README screenshots), 6b0d3ab (walkthroughs made), 1fa6918 (Setup asks ComfyUI
what it has), 9ef2c6c (underwater is the example theme), f08220e + d030044 (Cloud Final), 157fa82 (the Final is
LTX-2.5 with loose guides, here and on Comfy Cloud), 4050338 (the lead names the two objects), and the Pillow/CI
fix after it. 1076 tests passed before the audit fixes; run the suite again after them.

**LTX-2.5 morphs** (Tys asked for it by default, and it is): with its graph's own guides it cut rather than
morphed; with the end guide at 0.6, img_compression 30 and a lead sentence naming both objects
(`cloud_final.LOOSE`, `cloud_final.lead`) it morphs on three vibes tried. `final_tier.model()` picks it whenever
its four files are installed; `cloud_final` sends the same graph to Comfy Cloud. Proof sheets:
`Desktop\xeno_walkthrough_29oct\ltx25_loose_morphs_three_vibes.jpg` and `ltx25_guides_comparison.jpg`.

**Comfy Cloud**: Tys's plan is Creator ($35/mo, 3 API runs at once, ~7,400 credits a month; 11,924 remaining at
4 am). One 3 s morph came back in 58 s (28 s of GPU, about 6 credits). The key is the Windows user variable
`COMFY_ORG_API_KEY` (set with `C:\Projects\set_comfy_key.ps1`); desks must be started with it in their
environment. Scripts: `scratchpad/wt/cloud_test_25.py check|run` (free check / one clip).

**The walkthroughs** (docs/demo/walkthrough.md, short_voice.json, long_voice.json): drafts cut on 29 Oct in
`Desktop\xeno_walkthrough_29oct` (short in three Kokoro voices, long in af_heart, 720p review copies). They are
out of date on the tiers (no Cloud Final, "all local") and must be rebuilt after the freeze.

## What is left, in order

1. **The audit fixes.** `scratchpad/audit_plan.json` (the session's scratchpad: `C:\Users\tyson\AppData\Local\Temp\claude\C--Projects\7d414e75-aaf9-49cf-88fc-dcf26694d380\scratchpad\`) holds 89 confirmed findings in 11
   file-disjoint clusters with claim, evidence and fix each. Cluster 1 is done. Run clusters 2-11 as a workflow,
   one fixer and one reviewer per cluster, no two on the same file, then the full suite, then one commit per
   cluster in the repo's voice. Delegate: the engine and desk clusters (2 app.js, 3 ui.py/recipe, 4 dense/clip_cut/
   lane, 5 job_timing/batch, 6 models_setup) want the strongest model; the docs, MCP text, test and voice-copy
   clusters (7, 8, 9, 10, 11) are mechanical and go to a cheaper one. Reviewers can be cheaper too.
2. **Freeze the app** and restart desks 47324, 47325, 47326 on the final commit (with the key). Tys's desks only
   on his word.
3. **Rebuild the walkthroughs** (tools in `scratchpad/wt/`: `shots.py`, `long_shots.py`, `record_cards.py`,
   `cards/cards.html`, `to_mp4.py`, `assemble.py`, `plan_short.json`, `make_plan_long.py`; Kokoro in
   `C:\Projects\kokoro-tts`: `read.py`, `check.py`, `try_line.py`, `join.py`; memory note
   `xenoform-walkthrough-videos.md` lists the recorder's traps). Re-read only the changed lines, re-record only
   the shots whose screens changed (the Model row now has four chips), add an **Under the hood** chapter: Tys
   said the demo "is like a black box". Build it from a real job's files (`work/ui/jobs/ce8fe479`: features.json
   beats and sections, simple/simple.json shots with their effects, simple/chain.json, simple/portrait stills,
   local00-21.mp4 and fast00-21.mp4 morphs): the song's beats and drop, the shot plan, the chain of stills, one
   morph from its two stills through the prompt to the clip, the re-timing and effects, the cut; one card like
   `cards/cards.html`, five or six voice lines, 45 to 60 s in the long, one line in the short. Then assemble
   the short (three voices) and the long, make 720p review copies, send them to Tys.
4. **Showcase Finals on Cloud Final** (LTX-2.5): ask Tys for a credit budget first; a 30 s cut is about twelve
   morphs, about 70 credits and six minutes. Songs: `Desktop\suno-demos\batch2\XF_HipHop_BoomBap_01.mp3` (in the
   walkthrough now), `XF_Ambient_01.mp3`, `batch1\XF_DnB_Liquid_01_v1.mp3`; vibes None, neon-noir, liquid-gold.
   Put the best into the walkthrough's opening and result shots.
5. **Tys's own steps** (docs/CONTEST.md checklist): push, upload the short, replace `DEMO_VIDEO_URL` in README.md
   and CONTEST.md, post with #OpenSourceHiggsfield, submit the Typeform. Open choices he still owes: the Kokoro
   voice (af_heart, am_michael, bm_george), 16:9 or a 9:16 cut for the post.

## Facts a fixer may need

- Tiers: draft (LTX 0.9.5), fast (the Draft upscaled, `upscale_pass`), final (LTX-2.5 loose, else LTX-2.3),
  cloud (LTX-2.5 loose on Comfy Cloud, at most 16 morphs, the tick `cloud_final_ok` on every Make).
- The recorder desk 47326 serves the current code only after a restart; app.js and CSS reload without one.
- Measured: Draft about 12 s a morph; LTX-2.5 local 321-413 s a 3 s shot at 576x1024; LTX-2.3 Final 706 s with
  its upscale; Cloud 58 s wall. Fast Final upscale about 20 s a clip.
