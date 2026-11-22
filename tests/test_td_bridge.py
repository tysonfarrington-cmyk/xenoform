"""td/xenoform_bridge.py against a fake TouchDesigner that accepts only the parameter names of the real operators
(tests/fixtures/td_pars.json, read from the Python stubs of an installed TouchDesigner): the script has to build the network
of td/README.md without a parameter the build does not have, wire it the way the README says, and ask only for channels the
relay sends. TouchDesigner itself is not needed."""
import fnmatch
import json
import re
from pathlib import Path

import pytest

from xenoform import osc_relay

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "td" / "xenoform_bridge.py"
PARS = json.loads((ROOT / "tests" / "fixtures" / "td_pars.json").read_text(encoding="utf-8"))["ops"]


class FakeType:
    def __init__(self, name):
        self.name = name


class FakePar:
    def __init__(self, name):
        self.name, self.val, self.expr, self.default, self.min, self.max = name, None, None, None, None, None
        self.clampMin = self.clampMax = False

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if key == "expr" and value is not None:
            object.__setattr__(self, "val", None)


class FakePars:
    """op.par: a name the real operator has answers with a parameter, any other name with None (as TouchDesigner does)."""

    def __init__(self, owner):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_pars", {})

    def _allowed(self, name):
        return name in PARS.get(self._owner.optype, ()) or name in self._owner.custom

    def __getattr__(self, name):
        if name.startswith("_") or not self._allowed(name):
            return None
        return self._pars.setdefault(name, FakePar(name))

    def __setattr__(self, name, value):  # comp.par.opviewer = op
        if not self._allowed(name):
            raise AttributeError(name)
        self._pars.setdefault(name, FakePar(name)).val = value


class FakeConnector:
    def __init__(self):
        self.source = None

    def connect(self, target):
        self.source = target


class FakePage:
    def __init__(self, owner):
        self.owner = owner

    def _add(self, name, label=None, size=1, **kw):
        self.owner.custom.add(name)
        return [getattr(self.owner.par, name)]

    appendToggle = appendInt = appendFloat = appendFile = appendFolder = _add


class FakeOp:
    def __init__(self, optype, name, parent=None):
        self.optype, self.name, self.parent_op = optype, name, parent
        self.custom, self.children, self.text, self.comment = set(), {}, "", ""
        self.par = FakePars(self)
        self.inputConnectors = [FakeConnector() for _ in range(4)]
        self.outputConnectors = [FakeConnector()]
        self.nodeX = self.nodeY = 0
        self.saved = None

    @property
    def path(self):
        return (self.parent_op.path.rstrip("/") if self.parent_op else "") + "/" + self.name

    def create(self, opType, name):
        base, n = name, 0
        while name in self.children:
            n += 1
            name = f"{base}{n}"
        node = FakeOp(opType.name, name, self)
        self.children[name] = node
        return node

    def appendCustomPage(self, name):
        return FakePage(self)

    def save(self, filepath, createFolders=False):
        self.saved = filepath
        return filepath


def world(repo=None, build=False, source=None):
    """A fake /project1 and the namespace the script runs in (the way TouchDesigner's Textport runs it)."""
    root = FakeOp("baseCOMP", "project1", None)
    root.parent_op = None
    ns = {name: FakeType(name) for name in PARS}
    ns["op"] = lambda path: root if path == "/project1" else None
    if not build:
        ns["XENOFORM_NO_BUILD"] = True
    if repo:
        ns["XENOFORM_DIR"] = str(repo)
    exec(compile(source or SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), ns)
    return root, ns


@pytest.fixture
def repo(tmp_path):
    clip = tmp_path / "src" / "xenoform" / "ui_static" / "library" / "neon-night" / "wide.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    return tmp_path


def children(comp):
    return {k: v for k, v in comp.children.items()}


def test_the_script_builds_the_network_with_only_parameters_the_operators_have(repo):
    root, ns = world(repo)
    comp = ns["build"](repo=str(repo))
    assert comp.name == "xenoform_bridge" and comp.path == "/project1/xenoform_bridge"
    assert [n for n in ns["notes"] if not n.startswith("built ")] == [], "a parameter was skipped or refused: " + str(ns["notes"])
    kids = children(comp)
    for name in ("osc_in", "out_all", "bridge_util", "clips", "movie", "noise", "mix", "displace", "level", "out", "feedback", "fb_transform",
                 "fb_level", "sel_frame", "frame_slope", "updates_per_second", *[f"sel_{f}" for f in ns["FAMILIES"]], *[f"out_{f}" for f in ns["FAMILIES"]]):
        assert name in kids, f"{name} is missing"
    types = {k: v.optype for k, v in kids.items()}
    assert types["osc_in"] == "oscinCHOP" and types["movie"] == "moviefileinTOP" and types["feedback"] == "feedbackTOP"
    assert types["displace"] == "displaceTOP" and types["level"] == "levelTOP" and types["mix"] == "compositeTOP"


def test_the_fake_touchdesigner_does_refuse_a_parameter_the_operator_lacks(repo):
    """The harness itself: a misspelt parameter must show up in the script's notes, or the test above proves nothing."""
    bad = SCRIPT.read_text(encoding="utf-8").replace("displaceweightx=", "displaceweightq=").replace('"top"', '"topp"').replace("top=\"level\"", "toop=\"level\"")
    root, ns = world(repo, source=bad)
    ns["build"](repo=str(repo))
    joined = "\n".join(ns["notes"])
    assert "displace has no parameter displaceweightq" in joined and "feedback has no parameter toop" in joined


def test_the_network_is_wired_the_way_the_readme_says(repo):
    root, ns = world(repo)
    comp = ns["build"](repo=str(repo))
    k = children(comp)
    src = lambda node, i=0: node.inputConnectors[i].source
    assert src(k["mix"], 0) is k["movie"] and src(k["mix"], 1) is k["fb_level"]
    assert src(k["displace"], 0) is k["mix"] and src(k["displace"], 1) is k["noise"]
    assert src(k["level"]) is k["displace"] and src(k["out"]) is k["level"]
    assert src(k["feedback"]) is k["movie"] and src(k["fb_transform"]) is k["feedback"] and src(k["fb_level"]) is k["fb_transform"]
    assert k["feedback"].par.top.val == "level", "the feedback loop closes on the Level TOP"
    assert src(k["out_all"]) is k["osc_in"]
    for fam, pattern in ns["FAMILIES"].items():
        assert src(k["out_" + fam]) is k["sel_" + fam] and k["sel_" + fam].par.channames.val == pattern and k["sel_" + fam].par.chops.val == "osc_in"
    assert src(k["updates_per_second"]) is k["frame_slope"] and src(k["frame_slope"]) is k["sel_frame"] and k["sel_frame"].par.channames.val == "frame"
    assert k["osc_in"].par.stripprefixes.val == 1
    assert k["osc_in"].par.port.expr == "parent().par.Port" and k["osc_in"].par.active.expr == "parent().par.Active"


def test_the_component_has_its_xenoform_page_and_the_loop(repo):
    root, ns = world(repo)
    comp = ns["build"](repo=str(repo))
    assert comp.custom == {"Active", "Port", "Clip", "Clipfolder", "Displace", "Feedback", "Beatflash"}
    assert comp.par.Port.val == 7000 and comp.par.Port.default == 7000 and comp.par.Port.min == 1 and comp.par.Port.max == 65535
    assert comp.par.Active.val is True and comp.par.Feedback.max == 0.98
    assert comp.par.Clip.val.endswith("wide.mp4") and "library" in comp.par.Clipfolder.val
    assert comp.par.opviewer.val is children(comp)["out"]
    assert children(comp)["movie"].par.file.expr == "parent().par.Clip" and children(comp)["clips"].par.rootfolder.expr == "parent().par.Clipfolder"
    assert children(comp)["movie"].par.playmode.val == "sequential" and children(comp)["mix"].par.operand.val == "screen"


def test_without_a_checkout_it_says_where_the_loops_are():
    root, ns = world()
    comp = ns["build"]()
    assert any("no loop yet" in n and "ui_static/library" in n for n in ns["notes"])
    assert comp.par.Clip.val == "" and comp.par.Clipfolder.val == ""


def test_a_second_build_does_not_touch_the_first_and_the_tox_goes_where_asked(repo):
    root, ns = world(repo)
    first = ns["build"](repo=str(repo))
    first.children["osc_in"].par.port.expr = "7777"
    second = ns["build"](repo=str(repo), save_tox=True)
    assert first.name == "xenoform_bridge" and second.name == "xenoform_bridge1"
    assert first.children["osc_in"].par.port.expr == "7777"
    assert second.saved == str(repo / "td" / "xenoform_bridge.tox")
    with pytest.raises(RuntimeError, match="no network at /nowhere|There is no network at /nowhere"):
        ns["build"](where="/nowhere")


def test_exec_in_the_textport_builds_at_once(repo):
    root, ns = world(repo, build=True)  # no XENOFORM_NO_BUILD: the two-line recipe in the README
    assert "xenoform_bridge" in root.children and root.children["xenoform_bridge"].par.Clip is not None


def test_the_expressions_compile_and_ask_only_for_channels_the_relay_sends(repo):
    root, ns = world(repo)
    comp = ns["build"](repo=str(repo))
    sent = {a.split("/", 1)[1] if a.startswith("xenoform/") else a for a in (x.lstrip("/") for x in osc_relay.live_address_map())}
    asked, exprs = set(), 0
    for node in comp.children.values():
        for par in node.par._pars.values():
            if par.expr:
                exprs += 1
                compile(par.expr, f"{node.name}.{par.name}", "eval")
                asked.update(re.findall(r"c\('([a-z_/]+)'\)", par.expr))
    assert exprs >= 10 and {"bass", "beat_env", "mid"} <= asked
    assert asked <= sent, f"expressions ask for channels the relay does not send: {asked - sent}"


def test_every_numeric_channel_lands_in_a_select_family_and_the_names_work_with_a_slash_or_an_underscore(repo):
    root, ns = world(repo)
    families = ns["FAMILIES"]
    sample = ["param/intensity", "param/fx:3", "param/stem:1", "midi/cc/1/74", "midi/note/10/36"]
    names = [a for a, t, *_ in osc_relay.CHANNELS if "string" not in t and "<" not in a] + sample
    for name in names:
        for spelled in (name, name.replace("/", "_")):  # TouchDesigner builds spell a multi-part address either way
            hits = [f for f, pat in families.items() if any(fnmatch.fnmatchcase(spelled, p) for p in pat.split())]
            assert len(hits) == 1, f"{spelled} lands in {hits}"
    for addr, kind, *_ in osc_relay.CHANNELS:  # the two string channels are the ones no family takes
        if "string" in kind and "<" not in addr and addr != "midi":
            assert not any(fnmatch.fnmatchcase(addr, p) for pat in families.values() for p in pat.split())


def test_the_readme_lists_every_address_and_the_families_the_script_builds():
    readme = (ROOT / "td" / "README.md").read_text(encoding="utf-8")
    table = set(re.findall(r"^\| `(/xenoform/[^`]+)` \|", readme, re.M))
    assert table == {f"/xenoform/{a}" for a, *_ in osc_relay.CHANNELS}, "the address table is osc_relay.CHANNELS, row for row"
    for addr, kind, rng, group, meaning in osc_relay.CHANNELS:
        assert f"| `/xenoform/{addr}` | {kind} | {rng} |" in readme and meaning in readme, addr
    root, ns = world()
    for family, pattern in ns["FAMILIES"].items():
        assert f"| `sel_{family}` | `{pattern}` | `out_{family}` |" in readme, f"the by-hand table of the {family} family is the script's"
    assert "XENOFORM_DIR" in readme and 'exec(open(XENOFORM_DIR + r"\\td\\xenoform_bridge.py").read())' in readme
    assert "Alt+T" in readme and "Strip Prefix Segments" in readme and "Screen Grab TOP" in readme and "NDI In TOP" in readme
    for what in ("Feedback TOP", "Displace TOP", "Level TOP", "Composite TOP", "Movie File In TOP", "OSC In CHOP", "/api/footage", "param/"):
        assert what in readme, what
    assert "No `.tox` ships" in readme, "the README says plainly that no tox was exported"


def test_the_two_docs_point_at_each_other_and_at_files_that_exist():
    readme = (ROOT / "td" / "README.md").read_text(encoding="utf-8")
    osc = (ROOT / "docs" / "osc.md").read_text(encoding="utf-8")
    for text, base in ((readme, ROOT / "td"), (osc, ROOT / "docs")):
        for link in re.findall(r"\]\(([^)#]+\.md)\)", text):
            assert (base / link).resolve().is_file(), f"{link} does not exist"
    assert "td/README.md" in osc and "docs/osc.md" in readme


def test_the_helper_gives_a_channel_or_a_default_until_the_first_message():
    root, ns = world()
    helper = {}
    chans = {"bass": [0.75]}

    class Chop:
        def __getitem__(self, name):
            return chans.get(name)

    exec(ns["UTIL"], {"op": lambda path: Chop() if path == "out_all" else None}, helper)
    assert helper["c"]("bass") == 0.75 and helper["c"]("beat_env") == 0.0 and helper["c"]("beat_env", 0.3) == 0.3
    exec(ns["UTIL"], {"op": lambda path: None}, helper)
    assert helper["c"]("bass") == 0.0, "no OSC In yet is not an error"
