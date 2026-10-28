# fz-Telemac

[Telemac](http://www.opentelemac.org/) plugin for the [fz](https://github.com/Funz/fz) parametric computation framework
(Python successor of the Java [Funz plugin-Telemac](https://github.com/Funz/plugin-Telemac)).

## Features

- Input: a Telemac case directory (steering file `.cas`, geometry, boundary conditions, ...);
  variables `$(name)` and formulas `@{expression}` in any **text** file of the case; comment lines start with `/`.
- Run: `Telemac.sh` runs `telemac2d` from a local installation, or from the
  [`irsn/telemac-mascaret`](https://hub.docker.com/r/irsn/telemac-mascaret) image with docker, podman or apptainer/singularity.
- Output: time series of every result variable (`VARIABLES FOR GRAPHIC PRINTOUTS`) at the
  points, lines and grids of interest listed in `*.poi` files, plus a `telemac_status`.
  The Serafin result file is read by `telemac_poi.py` (numpy only: no PyTelTools, no Java).

## Requirements

- Python 3.9+, [fz](https://github.com/Funz/fz), numpy, bash;
- Telemac: a local installation (`telemac2d.py` on `PATH`, or `TELEMAC_CMD`), or docker/podman/apptainer.

## Installation

```bash
pip install git+https://github.com/Funz/fz.git
fz install Telemac        # copies .fz/models/Telemac.json and .fz/calculators/ into ./.fz
```

or clone this repository and work from its root (it contains `.fz/`).

## Usage

```python
import fz

results = fz.fzr(
    input_path="examples/Telemac/t2d_breach.cas/",   # case directory
    input_variables={},                               # no variable in the base case
    model="Telemac",                                  # .fz/models/Telemac.json
    calculators="localhost_Telemac",                  # .fz/calculators/localhost_Telemac.json
    results_dir="results",
)
print(results[["telemac_status", "T", "S_xylowercenter"]])
```

```python
import matplotlib.pyplot as plt

plt.plot(results["T"][0], results["S_xylowercenter"][0])
plt.xlabel("Time (s)"); plt.ylabel("Free surface (m)"); plt.grid(); plt.show()
```

### Parametric study

Put variables in the case files, e.g. the breach width and opening duration in `breach.txt`:

```bash
sed -i 's/^50\.0$/$(breach_width)/; s/^300\.0$/$(breach_delay)/' examples/Telemac/t2d_breach.cas/breach.txt
```

```python
results = fz.fzr("examples/Telemac/t2d_breach.cas/",
                 {"breach_width": [40, 50], "breach_delay": [200, 300]},
                 "Telemac", calculators=["localhost_Telemac"] * 2, results_dir="results_grid")

for i, row in results.iterrows():
    plt.plot(row["T"], row["S_xylowercenter"], label=f"width {row['breach_width']}, delay {row['breach_delay']}")
plt.legend(); plt.show()
```

With several calculators in parallel, set `TELEMAC_NCSIZE` (MPI processes per case, default: all CPUs)
so that the cases do not compete for the same cores.

## Input

| | |
|---|---|
| variable | `$(name)`, with a default value: `$(name~0.005)` |
| formula | `@{expression}` |
| comment line | `/` |

The steering file is the `*.cas` file of the case that sets `GEOMETRY FILE` (`FICHIER DE GEOMETRIE`).
All the files it references must be in the case directory.

The example `t2d_breach.cas` targets Telemac 9.0 (the default image): the boolean keywords
`COMPUTATION CONTINUED` and `BREACH`, removed in 9.0 (the files `PREVIOUS COMPUTATION FILE` and
`BREACHES DATA FILE` now activate these features), are commented out; uncomment them for Telemac 8 or older.

**Text files must be UTF-8 (or ASCII)**: fz treats a file it cannot decode as UTF-8 as binary,
and does not look for variables in it. Telemac files written in Latin-1 (accents in comments)
must be converted first, e.g. `iconv -f latin1 -t utf-8 breach.txt > tmp && mv tmp breach.txt`.

### Points of interest (`*.poi`)

One `name=spec` per line (`#` starts a comment), x/y in the mesh coordinates:

```
xylowercenter=2500,15                  # point: linear interpolation in its mesh triangle
node42=42                              # node number (1-based): raw node value
section=2500,15:10:2900,250            # line: 10 points from (2500,15) to (2900,250)
map=2500,15:10,10:2900,250             # grid: 10x10 points from corner (2500,15) to corner (2900,250)
.bigmap=2500,15:100,100:2900,250       # name starting with '.': written as CSV, not returned to fz
```

A point outside the mesh gives `NaN`.
`TELEMAC_POI_METHOD=nearest` takes the value of the nearest node instead of the interpolation
(behaviour of the Java plugin).

## Output

| Output | Content |
|---|---|
| `telemac_status` | `NORMAL END` (Telemac printed `My work is done`), `ERROR: <message>` (Telemac or plugin error), `NO END BANNER` (interrupted run), `NO OUTPUT` |
| `T` | times of the saved frames (s) |
| `<VAR>_<poi>` | values of variable `<VAR>` at POI `<poi>` along time: a list for a point or node, a list (time) of lists (points) for a line or grid |
| `xy_<poi>` | coordinates of the points of a line or grid |

`<VAR>` is the Telemac mnemonic of the variable: `U`, `V`, `C`, `H`, `S`, `B`, `F`, `Q`, `I`, `J`, `M`,
`D`, `W`, `L`, `MAXZ`, `TMXZ`, `MAXV`, `TMXV` are returned by the model (a variable missing from the result
file gives an empty value). Others (`K`, `E`, `US`, tracers, ...) are written as `<VAR>_<poi>.csv` in the
case results: add a line to `output` in `.fz/models/Telemac.json` to return them.

The CSV files (`T.csv`, `<VAR>_<poi>.csv`: one line per frame, one column per point; `xy_<poi>.csv`)
and the result file stay in each case directory. `telemac_poi.py` can also be used alone:

```bash
python3 .fz/calculators/telemac_poi.py -c case.cas case.poi          # RESULTS FILE of case.cas
python3 .fz/calculators/telemac_poi.py -r r2d.slf "p=2500,15" -v S,H  # given file, POI, variables
```

## Calculator

`.fz/calculators/localhost_Telemac.json` runs `bash .fz/calculators/Telemac.sh` on the local host.
Telemac is found from, in this order:

1. `TELEMAC_CMD` (e.g. `/opt/telemac/scripts/python3/telemac2d.py`; `TELEMAC_PROFILE` is sourced first if set);
2. `telemac2d.py` on `PATH`;
3. the container image `TELEMAC_IMAGE` (default `irsn/telemac-mascaret:latest`) with `TELEMAC_CONTAINER`
   (default: the first of docker, podman, apptainer, singularity found).

Other settings: `TELEMAC_MODULE` (default `telemac2d`), `TELEMAC_NCSIZE`, `TELEMAC_OPTS` (extra launcher
options, e.g. `-c <config>`), `TELEMAC_CONTAINER_OPTS` (e.g. `--user 1000:1000` for docker),
`TELEMAC_POI_METHOD`, `TELEMAC_PYTHON` (python with numpy for the POI extraction).

Exit codes of `Telemac.sh` (non-zero: the fz case is failed):

| Code | Meaning |
|---|---|
| 0 | normal end |
| 1 / 2 | no steering file / usage |
| 3 | non-ASCII working path (not supported by Telemac) |
| 4 | Telemac not found |
| 5 | Telemac failed (exit code of the launcher; reason in `out.txt`/`err.txt`) |
| 6 | no result file after the run |
| 7 | POI extraction failed |

For remote calculators (`ssh://`, `slurm://`), `Telemac.sh` and `telemac_poi.py` must be installed side by
side on the remote host (e.g. `fz install Telemac` there), with the alias URI pointing to that path.

## Repository layout

```
.fz/models/Telemac.json                model: syntax and outputs
.fz/calculators/localhost_Telemac.json calculator alias (local run)
.fz/calculators/Telemac.sh             runs Telemac, then the POI extraction
.fz/calculators/telemac_poi.py         Serafin reader and POI extraction (numpy)
examples/Telemac/t2d_breach.cas/       dyke breach case (Telemac 2D)
tests/                                 pytest suite
```

## Tests

```bash
pip install pytest numpy
pytest tests/
```

No Telemac installation is needed: the tests use a real Telemac 2D result of the example (3 of its 46
frames, `tests/fixtures/t2d_breach/`), the CSV files written by the Java plugin from the full result
(`tests/fixtures/java_plugin/`, compared with the `nearest` method), synthetic Serafin files, and a fake
Telemac launcher for the `fzr` runs. `tests/fixtures/telemac9/` holds the listings of real runs with the
`irsn/telemac-mascaret` image (Telemac 9.0: normal end, unknown keyword, missing file, Fortran stop), used to
check `telemac_status`.

## Limitations

- 2D results only (triangular mesh, e.g. `telemac2d`); 3D prism meshes are rejected by `telemac_poi.py`.
- Coordinates are taken as stored in the result file: the mesh origin offsets (`IPARAM(3:4)`) are not added.
- With docker, the result files of the case belong to root unless `TELEMAC_CONTAINER_OPTS` sets a user.
- The container run has not been tested by the CI (no Telemac image there): only the local launcher path is.

## License

BSD 3-Clause License.

## References

- [Telemac website](http://www.opentelemac.org/), [source code](https://gitlab.pam-retd.fr/otm/telemac-mascaret)
- [fz framework](https://github.com/Funz/fz)
