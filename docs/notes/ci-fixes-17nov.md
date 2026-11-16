# The smoke CI fixes (17 Nov 2026)

The public repo's `smoke` workflow (job `install-and-smoke`) went red on main at fd7ce76: 7 failed, 1675 passed, run
41277763077. Nothing in the code had changed; `ubuntu-latest` had moved to Ubuntu 26.04 with a newer ffmpeg, and the
workflow runs with `XENO_OFFLINE=1`. These fixes sit on `integrate-4nov` so they go out with the 4 Nov round.

Checked first: all seven tests still exist on this branch, in the same shape as at fd7ce76 (the code they test moved
in places; the failures did not). Six of the seven pass on this Windows machine with `XENO_OFFLINE=1` and the
ffmpeg that wrote the fixtures, so their red is the Linux runner's; only the film-pack one failed here too.

| failure | cause | fix | verified |
| --- | --- | --- | --- |
| `test_clip_moods::test_pack_json_and_labels_json_carry_the_fields_and_scan_hands_them_on`: `PlainError` at `film_pack.start()` | The test mocks the download (`RUNNER` copies a tiny clip) but leaves `XENO_OFFLINE=1` from the workflow in place, and `start()` refuses to begin a download offline, which is right for the desk. | The test clears `XENO_OFFLINE` as `test_film_pack.py`'s `pack` fixture does; the code is unchanged. | Passes here with `XENO_OFFLINE=1` set outside. |
| `test_clips_legacy[wobble_whole_wild]`: the compositor's arguments differ | The only argument that differs is `tones`, the dither's palette, which `effects.palette_from_clips` measures from the clips' decoded pixels. The test encodes those clips itself with the machine's ffmpeg; x264 of another version writes other bytes for the same seeded noise, so the measured tones move a few levels. H.264 decoding is bit-exact, so the clips encoded on one build look the same everywhere; it is the encode that differs. | `same_kw` in the test compares every argument exactly except `tones`, which must have the same count and each channel within 12 levels of the mainline's. | Passes here (identical). The size of the drift on Linux is only seen in CI. |
| `test_clips_legacy::test_the_composed_clips_cut_is_the_mainlines_byte_for_byte`: sha256 differs | The composed mp4's bytes are the encoder version's. | `tests/video_sig.py`: `luma_signature` decodes the file small and keeps the mean grey level of every frame with the size and frame rate; `same_picture` compares two within a tolerance (every frame within 6 levels, the average gap under 2, the frame count within 1). The fixture's real entry now carries the `ffmpeg` build that wrote it and the file's `signature`; on that build the test still asserts the sha256, on any other it asserts the picture. The signature was taken here from a composed file whose sha256 equals the fixture's, so it is the mainline's picture. | Passes here on the sha256 path; the signature path was exercised on the stored signature (identical passes, one frame short passes, one frame off by 9 fails, a uniform shift of 3 fails, another size fails). |
| `test_taste_absent::test_the_composed_file_with_no_taste_file_is_the_mainlines_byte_for_byte`: sha256 differs | The same. Its real case also measures `tones` from the mock engine's encoded cross-fades. | The same helpers and fixture fields; `same_kw` on its compose and re-cut arguments too. The fixture stays compact JSON as it was. | Same as above. |
| `test_limits`: `No module named 'tests'` | `from tests.test_music_video import` needs the repo root on `sys.path`. `python -m pytest` puts the working directory there; CI runs `.venv/bin/pytest`, which does not. The tests folder has no `__init__.py`, so pytest puts the folder itself on `sys.path` and the module is `test_music_video`. | The test imports `test_music_video` by that name. | Passes here with `pytest.exe` from the repo root. |
| `test_stems_api::test_background_split_reports_a_failed_split_and_tries_again_next_time`: the retry answers `error` | A real race in `stems_api.start_background_split`: it started the worker thread and only then took the status snapshot it answers with. A split that fails at once (the test's does) can finish before the snapshot, so the request that queued it answers `error` instead of `queued`. Linux starts the thread fast enough to show it; here it took four parallel runs to not show it. `start_own_split` already snapshots before starting. | The snapshot is taken inside the lock, before `t.start()`, so the request's own answer is always `queued`. The later status polls are unchanged. | The test passes here; the race itself can only be shown on the Linux runner. |
| `test_stress_pass::test_the_stems_line_gets_a_reason_in_plain_words`: a Windows path's basename comes back whole | `stems_api._reason` used `Path(filename).name` for an `OSError`; on Linux `Path` is a POSIX path and a Windows torch cache path has no separator it knows. | The name is taken after the last `\` or `/`, whichever the path uses. | Passes here; the Linux case is the same code path with a string that has only backslashes. |

Two more, not in the red run because their tests are newer than fd7ce76 (setup-shell, 4 Nov), found by running the
whole suite here with `XENO_OFFLINE=1` as CI does:

| failure | cause | fix | verified |
| --- | --- | --- | --- |
| `test_setup_final::test_a_download_that_does_not_fit_the_drive_says_why_and_never_starts` and `::test_a_card_too_small_for_the_final_is_told_so_instead_of_offered_forty_gigabytes` | `models_setup.why_not_download` gives the offline reason before the drive's, and gives it where a model that fits should have no reason. Both tests assume no `XENO_OFFLINE` in the environment. | Both tests clear `XENO_OFFLINE`; the order of reasons in the code stands (offline is the first truth about a download). | Both files pass here with and without the flag. |

The workflow (`.github/workflows/ci.yml`):

- `runs-on: ubuntu-24.04`, pinned with a comment, so a silent runner move cannot redden the suite again.
- `actions/checkout@v5` and `actions/setup-python@v6`, both past the Node 20 deprecation.

Tests run here (Windows, ffmpeg 8.1.1 gyan build, `XENO_OFFLINE=1`, `pytest -o addopts= -q -rfE`, since this repo's
`-q` in `addopts` makes a second `-q` silence the summary line):

- The six affected files: 46 passed, 1 skipped (the fixture builder, which needs `XENO_BUILD_CLIPS_FIXTURE`).
- The full suite as CI runs it (`--ignore` on `test_install.py` and `test_eligibility.py`): 1960 passed, 2 skipped,
  2 failed in 11:58, the two failures being the `test_setup_final` pair above, fixed after that run; their file then
  passed with and without the flag (27 tests with `test_clip_moods.py`). The suite was not run a second time whole.

Only verifiable in CI:

- That the tones tolerance (12 levels a channel) covers the drift of Ubuntu 24.04's x264 against the gyan build's.
- That the picture tolerance (6 levels a frame, 2 on average, a frame either way) covers the two builds' encodes of
  the same cross-fades at 192x108.
- That the stems retry no longer answers `error` on a fast thread start.
- That `actions/checkout@v5` and `actions/setup-python@v6` resolve and that `ubuntu-24.04` has an ffmpeg the suite's
  other tests are happy with (they passed on 26.04's).

Left:

- If CI shows a tones or picture gap larger than the tolerances, widen them in `TONE_LEVELS` or `same_picture`'s
  arguments with the measured gap written down, rather than going back to bytes.
- The fixture builders (`XENO_BUILD_CLIPS_FIXTURE`) now record `ffmpeg` and `signature` for the real case when they
  are next run on a scratch export, through the same spy that records the sha256.
