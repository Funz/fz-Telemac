"""End-to-end run through fz (fzr) with a fake Telemac launcher (TELEMAC_CMD).

The fake telemac2d.py checks the compiled steering file, then copies the real
result fixture to the RESULTS FILE and prints the end banner of runcode.py. Checks
the whole chain: calculator alias discovery (localhost_Telemac), the arguments
fz passes to Telemac.sh, POI extraction by telemac_poi.py, output parsing.

Run: pytest tests/test_fz_e2e.py
"""

import os
import shutil

import pytest

from conftest import ROOT

fz = pytest.importorskip("fz")

RESULT = ROOT / "tests" / "fixtures" / "t2d_breach" / "r2d_breach.slf"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")

FAKE = """#!/bin/bash
for a in "$@"; do case "$a" in --ncsize=*) n="${a#--ncsize=}" ;; *.cas) cas="$a" ;; esac; done
[ "$n" = 2 ] || { echo "ncsize=$n" >&2; exit 1; }
grep -q '^INITIAL ELEVATION *=2.5$' "$cas" || { printf '\\n\\nHummm ... I could not complete my work.\\n~~~~\\n\\nError: INITIAL ELEVATION not substituted\\n' >&2; exit 1; }
cp '%s' r2d_breach.slf
printf '\\n... processing the steering file\\n\\n\\nMy work is done\\n\\n'
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    shutil.copytree(ROOT / ".fz", tmp_path / ".fz")
    case = tmp_path / "t2d_breach.cas"
    shutil.copytree(ROOT / "examples" / "Telemac" / "t2d_breach.cas", case)
    cas = case / "t2d_breach.cas"
    cas.write_text(cas.read_text().replace("INITIAL ELEVATION        =2.0", "INITIAL ELEVATION        =$(z0)"))
    fake = tmp_path / "bin" / "telemac2d.py"
    fake.parent.mkdir()
    fake.write_text(FAKE % RESULT)
    fake.chmod(0o755)
    monkeypatch.setenv("TELEMAC_CMD", str(fake))
    monkeypatch.setenv("TELEMAC_NCSIZE", "2")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_fzi(workspace):
    assert list(fz.fzi("t2d_breach.cas", "Telemac")) == ["z0"]


@pytest.mark.parametrize("calculators", ["localhost_Telemac", None])
def test_fzr(workspace, calculators):
    kwargs = {"calculators": calculators} if calculators else {}
    results = fz.fzr("t2d_breach.cas", {"z0": [2.5]}, "Telemac",
                     results_dir=str(workspace / "results"), **kwargs)
    row = results.iloc[0]
    assert row["status"] == "done", row.to_dict()
    assert row["telemac_status"] == "NORMAL END"
    assert row["T"] == [0.0, 1320.0, 2700.0]
    for p in ("xylowercenter", "xymediumcenter", "xylowerright", "xymediumright"):
        assert len(row["S_" + p]) == 3 and len(row["H_" + p]) == 3
    assert row["S_xylowercenter"][-1] == pytest.approx(6.3825, abs=1e-4)  # nearest node (Java plugin): 6.3784


def test_fzr_failed_case(workspace):
    """Telemac exits 1 (runcode.py error): the case is failed, with the error as status."""
    results = fz.fzr("t2d_breach.cas", {"z0": [3.0]}, "Telemac", calculators="localhost_Telemac",
                     results_dir=str(workspace / "results"))
    row = results.iloc[0]
    assert row["status"] != "done"
    assert row["telemac_status"] == "ERROR: Error: INITIAL ELEVATION not substituted"


def test_fzr_telemac_not_found(workspace, monkeypatch):
    monkeypatch.setenv("TELEMAC_CMD", str(workspace / "bin" / "nothing.py"))
    results = fz.fzr("t2d_breach.cas", {"z0": [2.5]}, "Telemac", calculators="localhost_Telemac",
                     results_dir=str(workspace / "results"))
    row = results.iloc[0]
    assert row["status"] != "done"
    assert row["telemac_status"].startswith("ERROR: Telemac launcher not found")


def test_fzr_no_result_file(workspace, monkeypatch):
    """Telemac exits 0 without writing the RESULTS FILE: Telemac.sh exits 6, the case is failed."""
    fake = workspace / "bin" / "noresult.py"
    fake.write_text("#!/bin/bash\nprintf '\\nMy work is done\\n'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("TELEMAC_CMD", str(fake))
    results = fz.fzr("t2d_breach.cas", {"z0": [2.5]}, "Telemac", calculators="localhost_Telemac",
                     results_dir=str(workspace / "results"))
    row = results.iloc[0]
    assert row["status"] != "done"
    assert row["telemac_status"].startswith("ERROR: cannot read ")
    assert "r2d_breach.slf" in row["telemac_status"]


def test_example_files_are_parametrizable(workspace):
    """fz skips non-UTF-8 text files as binary: the example text files must stay UTF-8."""
    case = workspace / "t2d_breach.cas"
    for f in ("t2d_breach.cas", "breach.txt", "t2d_breach.liq", "geo_breach.cli", "t2d_breach.poi"):
        (case / f).read_bytes().decode("utf-8")
    txt = case / "breach.txt"
    txt.write_text(txt.read_text().replace("\n50.0\n", "\n$(breach_width)\n", 1))
    assert set(fz.fzi("t2d_breach.cas", "Telemac")) == {"z0", "breach_width"}


@pytest.mark.parametrize("container,expected", [
    ("docker", "run --rm -e I_MPI_HYDRA_BOOTSTRAP=fork -e I_MPI_ROOT_GTOOL_BYPASS=1 -v {pwd}:/workdir -w /workdir "
               "irsn/telemac-mascaret:latest telemac2d.py --ncsize=2 t2d_breach.cas"),
    ("podman", "run --rm -e I_MPI_HYDRA_BOOTSTRAP=fork -e I_MPI_ROOT_GTOOL_BYPASS=1 -v {pwd}:/workdir -w /workdir "
               "--ipc=host docker.io/irsn/telemac-mascaret:latest telemac2d.py --ncsize=2 t2d_breach.cas"),
    ("apptainer", "run -B {pwd}:/workdir -H /workdir docker://irsn/telemac-mascaret:latest "
                  "telemac2d.py --ncsize=2 t2d_breach.cas"),
])
def test_container_command(workspace, monkeypatch, container, expected):
    """Without TELEMAC_CMD nor telemac2d.py on PATH, Telemac.sh runs the container image."""
    fake = workspace / "cbin" / container
    fake.parent.mkdir()
    fake.write_text('#!/bin/bash\necho "$@" > container_args\n'
                    f"cp '{RESULT}' r2d_breach.slf\nprintf 'My work is done\\n'\n")
    fake.chmod(0o755)
    monkeypatch.delenv("TELEMAC_CMD")
    monkeypatch.setenv("TELEMAC_CONTAINER", container)
    monkeypatch.setenv("PATH", "%s:%s" % (fake.parent, os.environ["PATH"]))
    results = fz.fzr("t2d_breach.cas", {"z0": [2.5]}, "Telemac", calculators="localhost_Telemac",
                     results_dir=str(workspace / "results"))
    row = results.iloc[0]
    assert row["status"] == "done", row.to_dict()
    args = (workspace / "results" / "z0=2.5" / "container_args").read_text().strip()
    pwd = args.split(":/workdir")[0].split()[-1]
    assert args == expected.format(pwd=pwd)
    assert len(row["S_xylowercenter"]) == 3
