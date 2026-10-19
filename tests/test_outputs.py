"""Output extraction of the Telemac model (.fz/models/Telemac.json).

The CSV files are produced by telemac_poi.py from the real result fixture.
Listings (out.txt/err.txt):
- tests/fixtures/telemac9/: real runs of Telemac.sh with the irsn/telemac-mascaret
  image (Telemac 9.0), paths anonymized: ok_t2d_breach (the example, listing trimmed
  in the middle), err_unknown_keyword (BREACH = YES, removed in 9.0),
  err_missing_file (no ini_breach.slf), err_plante (Fortran stop: TIME STEP = 1.E30
  out of the liquid boundaries file);
- synthetic: messages of scripts/python3/runcode.py in the current telemac-mascaret
  sources ("Hummm ... I could not complete my work." on stderr), of Telemac.sh and
  of telemac_poi.py.

Run: pytest tests/test_outputs.py
"""

import json
import math
import shutil

import numpy as np
import pytest

import telemac_poi as tp
from conftest import ROOT

fz = pytest.importorskip("fz")

MODEL = json.loads((ROOT / ".fz" / "models" / "Telemac.json").read_text())
RESULT = ROOT / "tests" / "fixtures" / "t2d_breach" / "r2d_breach.slf"


def outputs(path):
    return fz.fzo(str(path), MODEL).iloc[0].to_dict()


def missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


@pytest.fixture
def case(tmp_path):
    shutil.copy(RESULT, tmp_path)
    (tmp_path / "out.txt").write_text("... processing the steering file\n\n\nMy work is done\n\n\n")
    poi = {"xylowercenter": "2500,15", "line": "2500,15:3:2900,250", ".big": "2500,15:5,5:2900,250"}
    data = tp.extract(tp.Serafin(str(tmp_path / "r2d_breach.slf")), poi)
    for stem, a in data.items():
        tp.write_csv(tmp_path / (stem + ".csv"), a)
    return tmp_path, data


FIXTURES9 = ROOT / "tests" / "fixtures" / "telemac9"


@pytest.mark.parametrize("case_dir,status", [
    ("ok_t2d_breach", "NORMAL END"),
    ("err_unknown_keyword", "ERROR: Unknown keyword BREACH in steering file t2d_breach.cas"),
    ("err_missing_file", "ERROR: In t2d_breach.cas missing file for PREVIOUS COMPUTATION FILE: ini_breach.slf"),
    ("err_plante", "ERROR: THE LIQUID BOUNDARIES FILE CONTAINS 3 LINES WITH: SL(1) Q(2) "
                   "T= 1.000000000000000E+030 OUT OF RANGE OF THE FILE OF LIQUID BOUNDARIES "
                   "NUMBER OF LINES : 3 SOME COMPILERS REQUIRE AN EMPTY LINE AT THE END OF THE FILE"),
])
def test_status_real_telemac9(case_dir, status):
    assert outputs(FIXTURES9 / case_dir)["telemac_status"] == status


def test_outputs_from_csv(case):
    path, data = case
    out = outputs(path)
    assert out["telemac_status"] == "NORMAL END"
    assert out["T"] == [0.0, 1320.0, 2700.0]
    assert out["S_xylowercenter"] == pytest.approx(data["S_xylowercenter"][:, 0].tolist())
    assert np.array(out["H_line"]).shape == (3, 3)
    assert np.array(out["H_line"]) == pytest.approx(data["H_line"])
    assert out["xy_line"][0] == [2500.0, 15.0]
    assert not any(k.endswith(".big") for k in out), "POI starting with '.' must be ignored"
    for v in ("C", "F", "Q", "MAXZ"):  # not in VARIABLES FOR GRAPHIC PRINTOUTS
        assert missing(out[v])


def test_no_output(tmp_path):
    (tmp_path / "t2d_breach.cas").write_text("TITLE = 'x'\n")
    out = outputs(tmp_path)
    assert out["telemac_status"] == "NO OUTPUT"
    assert missing(out["T"]) and missing(out["S"])


def test_no_end_banner(tmp_path):
    (tmp_path / "out.txt").write_text("... processing the steering file\n ITERATION 120 TIME 60 S\n")
    assert outputs(tmp_path)["telemac_status"] == "NO END BANNER"


def test_runcode_error(tmp_path):
    (tmp_path / "out.txt").write_text("... processing the steering file\n")
    (tmp_path / "err.txt").write_text(
        "\n\nHummm ... I could not complete my work.\n" + "~" * 72 + "\n\n"
        "Error: file geo_breach.slf does not exist\n")
    assert outputs(tmp_path)["telemac_status"] == "ERROR: Error: file geo_breach.slf does not exist"


def test_fortran_stop(tmp_path):
    (tmp_path / "out.txt").write_text(" ITERATION 10\n PLANTE: PROGRAM STOPPED AFTER AN ERROR\n")
    assert outputs(tmp_path)["telemac_status"] == "ERROR: PLANTE: PROGRAM STOPPED AFTER AN ERROR"


def test_script_error(tmp_path):
    (tmp_path / "out.txt").write_text("")
    (tmp_path / "err.txt").write_text(
        "Telemac not found: set TELEMAC_CMD, put telemac2d.py on PATH, or install docker/podman/apptainer\n")
    assert outputs(tmp_path)["telemac_status"].startswith("ERROR: Telemac not found")


def test_poi_extraction_error(tmp_path):
    """Telemac ended normally but the POI extraction failed (Telemac.sh exit code 7)."""
    (tmp_path / "out.txt").write_text("My work is done\n")
    (tmp_path / "err.txt").write_text("warning: POI a: 1 point(s) outside the mesh (NaN)\n"
                                      "error: POI b: node 99999 out of range 1..13648\n")
    assert outputs(tmp_path)["telemac_status"] == "ERROR: POI b: node 99999 out of range 1..13648"
