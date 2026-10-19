"""POI extraction from Serafin result files (.fz/calculators/telemac_poi.py).

Fixtures:
- tests/fixtures/t2d_breach/r2d_breach.slf: real Telemac 2D v8p2 result of the
  t2d_breach example (frames 0, 22 and 45 of the 46 saved frames, all variables);
- tests/fixtures/java_plugin/: CSV files written by the Java Funz plugin
  (plugin-Telemac) from the full result file; that plugin returned the value of
  the nearest node, so they are compared with --method nearest;
- synthetic Serafin files written by conftest.write_serafin.

Run: pytest tests/test_poi.py
"""

import subprocess
import sys

import numpy as np
import pytest

import telemac_poi as tp
from conftest import ROOT, write_serafin

FIXTURES = ROOT / "tests" / "fixtures"
RESULT = FIXTURES / "t2d_breach" / "r2d_breach.slf"
JAVA = FIXTURES / "java_plugin"
FRAMES = [0, 22, 45]  # frames kept in the truncated fixture
POINTS = ["xylowercenter", "xymediumcenter", "xylowerright", "xymediumright"]
SCRIPT = ROOT / ".fz" / "calculators" / "telemac_poi.py"


@pytest.fixture(scope="module")
def slf():
    return tp.Serafin(str(RESULT))


# --- real result file ---

def test_header(slf):
    assert slf.title.startswith("TELEMAC 2D : rupture digue")
    assert [tp.short_name(n) for n in slf.var_names] == ["U", "V", "H", "S", "B", "D", "W", "L"]
    assert (slf.npoin, slf.nelem, slf.ndp) == (13648, 26449, 3)
    assert slf.nframes == 3
    assert slf.times.tolist() == np.loadtxt(JAVA / "T.csv")[FRAMES].tolist()


@pytest.mark.parametrize("var,java", [("U", "U"), ("V", "V"), ("H", "H"), ("S", "S"), ("B", "B"),
                                      ("D", "null"), ("W", "W"), ("L", "L")])
def test_nearest_matches_java_plugin(slf, var, java):
    poi = tp.read_poi_file(JAVA / "t2d_breach.poi")
    del poi["XY"]  # grid: the Java version that wrote the references excluded the end corner
    out = tp.extract(slf, poi, [var], method="nearest")
    for p in POINTS:
        ref = np.loadtxt(JAVA / ("%s_%s.csv" % (java, p)))[FRAMES]
        assert out["%s_%s" % (var, p)][:, 0] == pytest.approx(ref, rel=1e-6, abs=2e-6), p


def test_linear_between_triangle_values(slf):
    """Linear interpolation stays within the values of the 3 nodes of the triangle."""
    pts = [(2500, 15), (2500, 250), (2900, 15), (2900, 250)]
    nodes, weights = tp.interpolators(slf, pts)
    assert np.all(weights >= -1e-9) and weights.sum(axis=1) == pytest.approx(1)
    h = slf.frame(2)[2]
    for n, w in zip(nodes, weights):
        v = (h[n] * w).sum()
        assert h[n].min() - 1e-6 <= v <= h[n].max() + 1e-6


def test_linear_close_to_nearest(slf):
    poi = {p: s for p, s in tp.read_poi_file(JAVA / "t2d_breach.poi").items() if p in POINTS}
    lin = tp.extract(slf, poi, ["S"])
    near = tp.extract(slf, poi, ["S"], method="nearest")
    for p in POINTS:
        assert lin["S_" + p] == pytest.approx(near["S_" + p], abs=0.05)


def test_grid_and_line(slf):
    out = tp.extract(slf, {"map": "2500,15:11,11:2900,250", "line": "2500,15:5:2900,15", ".hidden": "1"}, ["H"])
    assert out["H_map"].shape == (3, 121)
    assert out["xy_map"][0].tolist() == [2500, 15] and out["xy_map"][-1].tolist() == [2900, 250]
    assert out["xy_map"][1].tolist() == [2540, 15]  # x varies first
    assert out["H_line"].shape == (3, 5)
    assert out["xy_line"][:, 0].tolist() == [2500, 2600, 2700, 2800, 2900]
    assert out["H_.hidden"][:, 0] == pytest.approx([slf.frame(i)[2][0] for i in range(3)])
    assert "xy_.hidden" not in out


def test_cli_with_cas(tmp_path):
    case = tmp_path / "case"
    case.mkdir()
    (case / "r2d_breach.slf").symlink_to(RESULT)
    (case / "t2d_breach.cas").write_text((ROOT / "examples" / "Telemac" / "t2d_breach.cas" / "t2d_breach.cas").read_text())
    (case / "t2d_breach.poi").write_text("xylowercenter=2500,15\n")
    r = subprocess.run([sys.executable, str(SCRIPT), "-c", str(case / "t2d_breach.cas"), str(case / "t2d_breach.poi")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in case.glob("*.csv")) == sorted(
        ["T.csv"] + ["%s_xylowercenter.csv" % v for v in "UVHSBDWL"])
    assert np.loadtxt(case / "T.csv").tolist() == [0, 1320, 2700]


@pytest.mark.parametrize("args,code", [
    (["-r", "missing.slf", "p=1,1"], 2),
    (["-r", str(RESULT), "p=1;1"], 1),
    (["-r", str(RESULT), "notafile"], 1),
    (["-r", str(RESULT), "p=99999"], 1),
])
def test_cli_errors(tmp_path, args, code):
    r = subprocess.run([sys.executable, str(SCRIPT), "-o", str(tmp_path)] + args, capture_output=True, text=True)
    assert r.returncode == code, r.stdout + r.stderr
    assert "error:" in r.stderr


# --- synthetic files ---

@pytest.mark.parametrize("endian,double", [(">", False), ("<", False), (">", True)])
def test_linear_exact_on_linear_field(tmp_path, square_mesh, endian, double):
    x, y, ikle = square_mesh
    f = lambda t: 1.5 + 2 * x - 0.5 * y + t  # noqa: E731
    path = tmp_path / "r.slf"
    write_serafin(path, x, y, ikle, [[f(0), -f(0)], [f(10), -f(10)]],
                  ["FREE SURFACE    M", "WATER DEPTH     M"], [0.0, 10.0], endian, double)
    slf = tp.Serafin(str(path))
    out = tp.extract(slf, {"a": "2.5,7.5", "b": "7,1", "c": "10,10", "out": "11,5", "n": "2"})
    for name, (px, py) in {"a": (2.5, 7.5), "b": (7, 1), "c": (10, 10)}.items():
        assert out["S_" + name][:, 0] == pytest.approx([1.5 + 2 * px - 0.5 * py + t for t in (0, 10)], abs=1e-5)
    assert np.isnan(out["S_out"]).all()
    assert out["S_n"][:, 0] == pytest.approx([21.5, 31.5])
    assert out["T"][:, 0].tolist() == [0.0, 10.0]


def test_duplicate_short_names(tmp_path, square_mesh):
    x, y, ikle = square_mesh
    path = tmp_path / "r.slf"
    write_serafin(path, x, y, ikle, [[x, y]], ["FREE SURFACE    M", "SURFACE LIBRE   M"], [0.0])
    out = tp.extract(tp.Serafin(str(path)), {"n": "3"})
    assert out["S_n"][0, 0] == 10 and out["S_2_n"][0, 0] == 10
    assert tp.var_names(tp.Serafin(str(path))) == ["S", "S_2"]


def test_incomplete_last_frame_ignored(tmp_path, square_mesh):
    x, y, ikle = square_mesh
    path = tmp_path / "r.slf"
    write_serafin(path, x, y, ikle, [[x], [x + 1]], ["WATER DEPTH     M"], [0.0, 1.0])
    data = path.read_bytes()
    path.write_bytes(data[:-10])  # run interrupted while writing the last frame
    assert tp.Serafin(str(path)).nframes == 1


def test_short_names():
    assert tp.short_name("HAUTEUR D'EAU") == "H"
    assert tp.short_name("VITESSE SCALAIRE") == "M"
    assert tp.short_name("1/R") == "1_R"
    assert tp.short_name("TRACER 1") == "TRACER1"


def test_read_poi_file(tmp_path):
    f = tmp_path / "a.poi"
    f.write_text("# header\n! java comment\n\npt = 2500,15   # point\nmap=2500,15:10,10:2900,250\n")
    assert tp.read_poi_file(f) == {"pt": "2500,15", "map": "2500,15:10,10:2900,250"}


def test_parse_spec():
    assert tp.parse_spec("1, 2") == ("points", [(1.0, 2.0)])
    assert tp.parse_spec("12") == ("node", [11])
    assert tp.parse_spec("0,0:3:2,4") == ("points", [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0)])
    kind, pts = tp.parse_spec("0,0:2,3:1,2")
    assert pts == [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)]
    with pytest.raises(ValueError):
        tp.parse_spec("0,0:1,1")


def test_cas_value(tmp_path):
    cas = tmp_path / "a.cas"
    cas.write_text("/ RESULTS FILE = 'commented.slf'\n"
                   "RESULTS FILE FORMAT = 'SERAFIN'\n"
                   "TITLE = 'a/b'  / RESULTS FILE = 'in_comment.slf'\n"
                   "FICHIER DES RESULTATS :\n  \"r 2d.slf\" / comment\n")
    assert tp.cas_value(cas, tp.RESULTS_KEYWORDS) == "r 2d.slf"
    cas.write_text("GEOMETRY FILE = geo.slf\n")
    assert tp.cas_value(cas, tp.RESULTS_KEYWORDS) is None
