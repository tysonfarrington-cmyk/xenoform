# Xenoform lessons

Living log of render lessons. Each row is a rule the desk already uses as a default or a Critic check. Lessons saved from Director's notes are appended here and stored as rules in `lessons.json` at the project root.

| Date | Lesson | Feature / default |
|---|---|---|
| 2026-10-17 | Half-speed slow-mo to beat-lock the dive made the ending limp ("plops down"). | Critic flag: slow-mo on an impact = anticlimax; beatlock prefers speed-up/trim into impacts, slow-mo only after impact. |
| 2026-10-17 | Wavy shimmer post effect ruins visuals. | Never a default; not offered as a preset. |
| 2026-10-17 | Bright bolt guide >0.3 blows out dark forms. | Guide-strength caps per recipe; exposure check in critic. |
| 2026-10-17 | LTX-2.3 mid guides >0.4 cause hard cuts; lands ~32f early. | Recipe defaults: mid guides <=0.4, end guides late; auto offset. |
| 2026-10-17 | Long soft dissolves ghost (double exposure). | Default dissolve <=8f with zoom-from-point regather. |
| 2026-10-17 | Fast low-res drafts beat polish for iteration speed. | Draft/Final modes; seeds+source-frame retime carry to Final. |
| 2026-10-17 | Iteration speed beats polish; draft fast, polish once. | Live / Turbo / Draft / Final. The browser picture is first. Seed 2727 and second-based retimes carry to Final. |
| 2026-10-17 | The browser picture is the cut that always exists. | Live plays with no model. Turbo, Draft, and Final are the optional passes. |
| 2026-10-17 | Stills posing as motion read dead; static spray rejected. | Critic freeze detector; real-fluid recipes (dive-splash, droplet-burst). |
| 2026-10-17 | Varied themes > polishing one clip for showing it's a tool. | Registers + dice presets as headline. |
| 2026-10-17 | Keyframe-to-keyframe morphs read as a blend. A cut wants shots. | Default is an action shot per card, hard-cut on the bar. A morph is a signature, once or twice, usually on the drop. Liquid metal is a Look. LTX-2.3 is the core video model. LTX 0.9.5 covers morphs and Turbo. Wan 2.2 is an optional open-weights alternative. |
| 2026-10-17 | A fresh-eyes pass ships the cut, or it asks for one more pass. | Review samples its own frames, every 0.2s and denser around cuts. It never reads the storyboard. The verdict is ship or one more pass. Fix the biggest problem, re-render, and the next pass rechecks the earlier items. |
| 2026-10-17 | If the silent contact sheet cannot tell the story, the story is unclear. | Sound-off test at 2 fps. The critic retells the picture without the track. |
| 2026-10-17 | The bar is measured. | Exact duration, size, and fps. Frame 1 is a finished picture. No still stretch over half a second, and under a second frozen in every thirty. Cuts and hits within one frame of the beat. Loudness about -14 LUFS, true peak at or under -1 dBTP, no clipping. Text at 4.5:1 inside the safe margins. Harding flash gate. |
| 2026-10-17 | Every review round writes its measurements down. | Before and after land in the ledger, markdown and JSON, and the version panel shows them. |
| 2026-10-17 | Pitch the treatment before the picture. | Two or three treatments, three named signature moments each. Then a style bible and three style frames. A 4 second Turbo proof plays before the full render. |
| 2026-10-17 | The picture locks to the audio. The music is not stretched. | timing.json holds the beats, the drops, and the key actions. Animation reads that file. A music-only export leaves the song alone. |
| 2026-10-17 | One subject, one lead move, a scale that changes. | Hard cuts only on the beat, with a matching size and direction. Effects earn the frame. Camera moves follow something on screen. Every varying number is a function of the seed and the frame. |
| 2026-10-17 | The phone changed shape in every opening shot, and the story looked cool but did not make sense. | One hero, one prop, one place. The same sentence and the same reference still go into every shot where they appear. Each shot follows from the last. Review re-renders only the shots that break it. |
