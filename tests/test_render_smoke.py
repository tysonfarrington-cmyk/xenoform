from xenoform.render_cpu import form_from_frame, render_frame


def _frame(**overrides):
    base = {
        "t": 1.25,
        "bass": 0.7,
        "sub": 0.4,
        "mid": 0.3,
        "high": 0.55,
        "onset_env": 0.8,
        "beat_env": 0.2,
        "mutate": 0.2,
        "energy": 0.5,
    }
    base.update(overrides)
    return base


def test_frame_has_a_bright_body_on_a_dark_field():
    form = form_from_frame(_frame())
    rgb, depth, mask = render_frame(form, 96, 54, max_steps=28)
    assert rgb.shape == (54, 96, 3)
    assert depth.shape == mask.shape == (54, 96)
    assert int(mask.sum()) > 0
    center = rgb[20:34, 36:60].astype("float32").mean()
    corner = rgb[0:8, 0:8].astype("float32").mean()
    assert center > corner + 8
    assert corner < 40


def test_drop_mutation_changes_the_silhouette():
    calm = render_frame(form_from_frame(_frame(mutate=0.0, onset_env=0.0, bass=0.2)), 64, 36, max_steps=24)[2]
    drop = render_frame(form_from_frame(_frame(mutate=1.0, onset_env=1.0, bass=0.95, t=2.0)), 64, 36, max_steps=24)[2]
    # Same resolution, different occupancy: the drop grows tendrils / shifts mass.
    assert abs(int(calm.sum()) - int(drop.sum())) > 0
