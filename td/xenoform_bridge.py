"""Xenoform -> TouchDesigner bridge: builds the network described in td/README.md inside TouchDesigner.

Run it in TouchDesigner's Textport (Alt+T), with the path of your Xenoform checkout:

    XENOFORM_DIR = r"C:\\path\\to\\xenoform"
    exec(open(XENOFORM_DIR + r"\\td\\xenoform_bridge.py").read())

It makes /project1/xenoform_bridge, a Base COMP, and nothing else in your project. Inside it:

    osc_in           OSC In CHOP on the port in the COMP's Xenoform page (7000); Strip Prefix Segments 1, so the channels are
                     named bass, beat_env, param/intensity ... (see the table in td/README.md)
    sel_* / out_*    a Select CHOP and a Null CHOP per family: audio, beat, show, stems, params, midi; out_all is everything
    updates_per_second   a rate meter: Slope CHOP of the frame counter, smoothed; reads about 60 while the live page streams
    clips, movie     a Folder DAT of the loops folder and a Movie File In TOP playing the loop in the Clip parameter
    noise, mix, displace, level, out, feedback, fb_transform, fb_level
                     the example: the loop is mixed (Screen) with its own feedback, displaced by animated noise as far as the
                     BASS channel says, brightened by BEAT_ENV on every beat; `out` is the picture
    bridge_util      a Text DAT with c(name): the value of an OSC channel, 0 until its first message arrives (so the
                     expressions never error before the desk starts streaming)

The COMP's Xenoform page: Active, Port, Clip (a movie file), Clipfolder, Displace (how far bass moves the picture), Feedback
(how much of the last frame stays), Beatflash (how much a beat brightens). To make a .tox of it: right-click the COMP,
Save Component .tox, or run build(save_tox=True) with XENOFORM_DIR set (writes td/xenoform_bridge.tox).

The names of parameters and the way the network is wired were checked against the Python stubs that ship with TouchDesigner
(2023/2024 builds); a parameter that a build does not have is skipped with a line in the Textport, never an error.
"""
import os

# The helper the expressions call (mod.bridge_util.c('bass')): an OSC channel's value, or a default until its first message.
UTIL = '''def c(name, default=0.0):
    """The value of an OSC channel by name (bass, beat_env, param/intensity ...), or default until a message for it has arrived."""
    chop = op("out_all")
    chan = chop[name] if chop is not None else None
    return float(chan[0]) if chan is not None else float(default)
'''

# One Select CHOP and one Null CHOP per family of channels. The patterns are what the desk sends (td/README.md has the table).
FAMILIES = {
    "audio": "rms sub bass mid high energy",
    "beat": "onset_env beat_env is_onset is_beat is_drop mutate",
    "show": "intensity transition transition_fx scene bpm beat time fps frame",
    "stems": "stem*",
    "params": "param*",
    "midi": "midi*",
}

LIBRARY = os.path.join("src", "xenoform", "ui_static", "library")  # the shipped vibe loops: <vibe>/<wide|reveal|close|medium>.mp4
FIRST_LOOPS = ("neon-night", "ferrofluid", "chrome-mercury", "cosmic")

notes = []


def _say(text):
    notes.append(text)
    print("xenoform_bridge: " + text)


def _set(o, **pars):
    """Set parameters by name; one a build does not have, or a value it refuses, is reported and skipped."""
    for name, value in pars.items():
        p = getattr(o.par, name, None)
        if p is None:
            _say("%s has no parameter %s here: skipped" % (o.name, name))
            continue
        try:
            p.val = value
        except Exception as exc:  # a menu token another build spells differently
            _say("%s.%s = %r was refused (%s): skipped" % (o.name, name, value, exc))


def _expr(o, **exprs):
    for name, text in exprs.items():
        p = getattr(o.par, name, None)
        if p is None:
            _say("%s has no parameter %s here: skipped" % (o.name, name))
            continue
        try:
            p.expr = text
        except Exception as exc:
            _say("%s.%s expression was refused (%s): skipped" % (o.name, name, exc))


def _first(o, names, value):
    """The same setting under the names different builds use (Strip Prefix Segments is stripprefixes or stripsegments)."""
    for name in names:
        if getattr(o.par, name, None) is not None:
            _set(o, **{name: value})
            return True
    _say("%s: none of %s exists here" % (o.name, "/".join(names)))
    return False


def _put(o, col, row):
    try:
        o.nodeX, o.nodeY = col * 220, -row * 130
    except Exception:
        pass
    return o


def _custom(comp, port, clip, folder):
    page = comp.appendCustomPage("Xenoform")

    def one(group, default, lo=None, hi=None):
        p = group[0]
        p.default = default
        p.val = default
        if lo is not None:
            p.min, p.clampMin = lo, True
        if hi is not None:
            p.max, p.clampMax = hi, True
        return p

    one(page.appendToggle("Active", label="OSC In active"), True)
    one(page.appendInt("Port", label="OSC port"), port, 1, 65535)
    one(page.appendFile("Clip", label="Loop (movie file)"), clip)
    one(page.appendFolder("Clipfolder", label="Loops folder"), folder)
    one(page.appendFloat("Displace", label="Bass displaces by"), 0.08, 0.0, 0.5)
    one(page.appendFloat("Feedback", label="Feedback kept"), 0.82, 0.0, 0.98)
    one(page.appendFloat("Beatflash", label="Beat brightens by"), 0.35, 0.0, 1.0)


def find_loops(repo):
    """(loops folder, first loop file) of a Xenoform checkout, '' where it is not found."""
    if not repo:
        return "", ""
    folder = os.path.join(repo, LIBRARY)
    for vibe in FIRST_LOOPS:
        for shot in ("wide", "medium", "close", "reveal"):
            path = os.path.join(folder, vibe, shot + ".mp4")
            if os.path.isfile(path):
                return folder, path
    return (folder if os.path.isdir(folder) else ""), ""


def build(where="/project1", name="xenoform_bridge", port=7000, repo=None, save_tox=False):
    """Make the bridge COMP inside `where` (a new numbered one if the name is taken) and return it."""
    del notes[:]
    here = op(where)
    if here is None:
        raise RuntimeError("There is no network at %s: pass where='/project1' or the path of one that exists." % where)
    folder, clip = find_loops(repo)
    comp = here.create(baseCOMP, name)
    comp.comment = "Xenoform live OSC: the desk's /vj page streams to the OSC In CHOP inside (port on the Xenoform page). td/README.md."
    _custom(comp, port, clip, folder)

    util = comp.create(textDAT, "bridge_util")
    util.text = UTIL
    _put(util, 0, 0)

    # ---- the channels
    osc = comp.create(oscinCHOP, "osc_in")
    _expr(osc, port="parent().par.Port", active="parent().par.Active")
    _first(osc, ("stripprefixes", "stripsegments"), 1)
    _put(osc, 0, 2)
    every = comp.create(nullCHOP, "out_all")
    every.inputConnectors[0].connect(osc)
    _put(every, 1, 2)
    for row, (family, pattern) in enumerate(FAMILIES.items()):
        sel = comp.create(selectCHOP, "sel_" + family)
        _set(sel, chops="osc_in", channames=pattern)
        nul = comp.create(nullCHOP, "out_" + family)
        nul.inputConnectors[0].connect(sel)
        _put(sel, 2, row + 1)
        _put(nul, 3, row + 1)
    frame = comp.create(selectCHOP, "sel_frame")
    _set(frame, chops="osc_in", channames="frame")
    slope = comp.create(slopeCHOP, "frame_slope")
    slope.inputConnectors[0].connect(frame)
    meter = comp.create(lagCHOP, "updates_per_second")
    meter.inputConnectors[0].connect(slope)
    _set(meter, lag1=0.5)
    _put(frame, 2, 7)
    _put(slope, 3, 7)
    _put(meter, 4, 7)

    # ---- the loop, and the example network it drives
    clips = comp.create(folderDAT, "clips")
    _expr(clips, rootfolder="parent().par.Clipfolder")
    _set(clips, subfolders=True)
    _put(clips, 0, 4)
    movie = comp.create(moviefileinTOP, "movie")
    _expr(movie, file="parent().par.Clip")
    _set(movie, playmode="sequential", textendleft="cycle", textendright="cycle")
    _put(movie, 6, 1)

    noise = comp.create(noiseTOP, "noise")  # the displacement map: red and green are the sideways and up-down pull
    _set(noise, type="simplex3d", period=0.35, amp=0.5, offset=0.5, mono=False)
    _expr(noise, tz="absTime.seconds * 0.25")
    _put(noise, 8, 3)

    mix = comp.create(compositeTOP, "mix")
    displace = comp.create(displaceTOP, "displace")
    level = comp.create(levelTOP, "level")
    out = comp.create(nullTOP, "out")
    feedback = comp.create(feedbackTOP, "feedback")
    fb_transform = comp.create(transformTOP, "fb_transform")
    fb_level = comp.create(levelTOP, "fb_level")

    mix.inputConnectors[0].connect(movie)
    mix.inputConnectors[1].connect(fb_level)
    displace.inputConnectors[0].connect(mix)
    displace.inputConnectors[1].connect(noise)
    level.inputConnectors[0].connect(displace)
    out.inputConnectors[0].connect(level)
    feedback.inputConnectors[0].connect(movie)  # what the loop starts from; `top` is what it feeds back
    fb_transform.inputConnectors[0].connect(feedback)
    fb_level.inputConnectors[0].connect(fb_transform)

    bass = "mod.bridge_util.c('bass')"
    beat = "mod.bridge_util.c('beat_env')"
    _set(mix, operand="screen")
    _expr(displace, displaceweightx="%s * parent().par.Displace" % bass, displaceweighty="%s * parent().par.Displace" % bass)
    _expr(level, brightness1="1 + parent().par.Beatflash * %s" % beat)
    _set(feedback, top="level")
    _expr(fb_transform, sx="1.008 + 0.03 * %s" % beat, sy="1.008 + 0.03 * %s" % beat, rotate="mod.bridge_util.c('mid') * 2")
    _expr(fb_level, opacity="parent().par.Feedback")
    for node, col, row in ((mix, 8, 1), (displace, 9, 2), (level, 10, 2), (out, 11, 2), (feedback, 6, 4), (fb_transform, 7, 4), (fb_level, 8, 4)):
        _put(node, col, row)
    try:
        comp.par.opviewer = out  # the COMP's tile in the network editor shows the picture
    except Exception:
        pass

    _say("built %s: OSC In on port %s, out = %s" % (comp.path, port, out.path))
    if not clip:
        _say("no loop yet: put a movie file in the Clip parameter of %s (the loops are in src/xenoform/ui_static/library/<vibe>/*.mp4)" % comp.path)
    if save_tox:
        target = os.path.join(repo, "td", "xenoform_bridge.tox") if repo else "xenoform_bridge.tox"
        _say("saved " + comp.save(target, createFolders=True))
    return comp


if "XENOFORM_NO_BUILD" not in globals():
    build(repo=globals().get("XENOFORM_DIR"))
