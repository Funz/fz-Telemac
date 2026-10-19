#!/usr/bin/env python3
"""Extract Telemac results at points of interest (POI) into CSV files.

Reads a Serafin result file (.slf/.res, single or double precision, either
endianness) with numpy only, and writes, in the output directory:

- T.csv               time of each saved frame (one value per line)
- <VAR>_<name>.csv    values of variable VAR at POI <name>: one line per frame,
                      one column per point (1 column for a single point)
- xy_<name>.csv       coordinates of the points of a line or grid POI

<VAR> is the short Telemac name of the variable (U, V, H, S, B, ... see
SHORT_NAMES), or the variable name without spaces when it has none.

POI file format (one "name=spec" per line; '#' starts a comment, '!' a comment line):

    pt=2500,15                  point x,y (linear interpolation in its triangle,
                                or nearest node value with --method nearest)
    node=1234                   node number (1-based, no interpolation)
    line=2500,15:10:2900,250    10 points evenly spaced from (2500,15) to (2900,250)
    map=2500,15:10,10:2900,250  10x10 grid from corner (2500,15) to corner (2900,250)

Names starting with '.' are extracted but meant to be ignored by the fz model
(e.g. large maps kept only on disk).

Usage:
    telemac_poi.py (-r RESULT.slf | -c CASE.cas) POI_FILE_OR_name=spec...
                   [-o OUTDIR] [-v U,H,S] [-m linear|nearest]

With -c, the result file is the RESULTS FILE (FICHIER DES RESULTATS) of the
steering file, relative to its directory.

Exit codes: 0 ok, 1 bad arguments or POI, 2 missing or unreadable result file.
"""

import argparse
import os
import re
import struct
import sys

import numpy as np

# Serafin variable names (16 first characters, English and French) -> mnemonic of
# "VARIABLES FOR GRAPHIC PRINTOUTS", from sources/telemac2d/nomvar_telemac2d.f
# (https://gitlab.pam-retd.fr/otm/telemac-mascaret).
SHORT_NAMES = {
    "VELOCITY U": "U", "VITESSE U": "U",
    "VELOCITY V": "V", "VITESSE V": "V",
    "CELERITY": "C", "CELERITE": "C",
    "WATER DEPTH": "H", "HAUTEUR D'EAU": "H",
    "FREE SURFACE": "S", "SURFACE LIBRE": "S",
    "BOTTOM": "B", "FOND": "B",
    "FROUDE NUMBER": "F", "FROUDE": "F",
    "SCALAR FLOWRATE": "Q", "DEBIT SCALAIRE": "Q",
    "TURBULENT ENERG.": "K", "ENERGIE TURBUL.": "K",
    "DISSIPATION": "E",
    "LONG. DISPERSION": "D", "VISCOSITY": "D", "DISPERSION LONG.": "D", "VISCOSITE TURB.": "D",
    "FLOWRATE ALONG X": "I", "DEBIT SUIVANT X": "I",
    "FLOWRATE ALONG Y": "J", "DEBIT SUIVANT Y": "J",
    "SCALAR VELOCITY": "M", "VITESSE SCALAIRE": "M",
    "WIND ALONG X": "X", "VENT X": "X",
    "WIND ALONG Y": "Y", "VENT Y": "Y",
    "AIR PRESSURE": "P", "PRESSION ATMOS.": "P",
    "BOTTOM FRICTION": "W", "FROTTEMENT": "W",
    "DRIFT ALONG X": "A", "DERIVE EN X": "A",
    "DRIFT ALONG Y": "G", "DERIVE EN Y": "G",
    "COURANT NUMBER": "L", "NBRE DE COURANT": "L",
    "HIGH WATER MARK": "MAXZ", "COTE MAXIMUM": "MAXZ",
    "HIGH WATER TIME": "TMXZ", "TEMPS COTE MAXI": "TMXZ",
    "HIGHEST VELOCITY": "MAXV", "VITESSE MAXIMUM": "MAXV",
    "TIME OF HIGH VEL": "TMXV", "T VITESSE MAXI": "TMXV",
    "FRICTION VEL.": "US", "VITESSE DE FROT.": "US",
    "TAU_S": "TAU_S",
    "1/R": "1/R",
    "WALLDIST": "WDIST", "DIST PAROI": "WDIST",
    "REFERENCE LEVEL": "ZRL",
    "INCREMENT OF H": "DH", "INCREMENT DE H": "DH",
    "INCREMENT OF U": "DU", "INCREMENT DE U": "DU",
    "INCREMENT OF V": "DV", "INCREMENT DE V": "DV",
    "INCREMENT OF HN": "DHN", "INCREMENT DE HN": "DHN",
    "SA VISCOSITY": "VISCSA", "VISCOSITE SA": "VISCSA",
    "O2 SAT CONC": "CSO2", "CONC SAT O2": "CSO2",
    "O2 SAT PERC": "O2SAT", "POURCENT SAT O2": "O2SAT",
    "HIGHEST DEPTH": "MAXH", "HAUTEUR MAXIMUM": "MAXH",
    "HIGHEST FLOWRATE": "MAXQ", "DEBIT MAXIMUM": "MAXQ",
    "TIME OF HIGH FLO": "TMXQ", "T DEBIT MAXIMUM": "TMXQ",
    "TIME OF SURGE AR": "TSAR", "T ARRIV. SURCOTE": "TSAR",
    "INIT WATER DEPTH": "H0", "HAUTEUR D'EAU 0M": "H0",
    "T SURGE AR FOUND": "ARRTRST", "T ARR SUR TROUVE": "ARRTRST",
}


def short_name(name):
    name = name.strip().upper()
    return re.sub(r"[^0-9A-Za-z_]", "_", SHORT_NAMES.get(name) or name.replace(" ", "")) or "VAR"


def var_names(slf):
    """Short names of the variables of a result file, made unique (S, S_2, ...)."""
    names = []
    for i, n in enumerate(slf.var_names):
        n = short_name(n)
        names.append(n if n not in names else "%s_%d" % (n, i + 1))
    return names


class Serafin:
    """Minimal Serafin reader: header, mesh, and frames on demand."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(4)
            if len(head) < 4:
                raise ValueError("empty file")
            if struct.unpack(">i", head)[0] == 80:
                self.endian = ">"
            elif struct.unpack("<i", head)[0] == 80:
                self.endian = "<"
            else:
                raise ValueError("not a Serafin file (bad first record)")
            f.seek(0)
            self.title = self._record(f).decode("latin-1")
            double = self.title[72:80].strip().upper() == "SERAFIND"
            self.float = np.dtype(self.endian + ("f8" if double else "f4"))
            nbv1, nbv2 = self._ints(f, 2)
            self.var_names, self.var_units = [], []
            for _ in range(nbv1 + nbv2):
                rec = self._record(f).decode("latin-1")
                self.var_names.append(rec[:16].strip())
                self.var_units.append(rec[16:32].strip())
            self.nvar = nbv1 + nbv2
            self.iparam = self._ints(f, 10)
            if self.iparam[9] == 1:
                self.date = self._ints(f, 6)
            self.nelem, self.npoin, self.ndp, _ = self._ints(f, 4)
            self.ikle = np.array(self._ints(f, self.nelem * self.ndp)).reshape(self.nelem, self.ndp) - 1
            self.ipobo = self._ints(f, self.npoin)
            self.x = self._floats(f, self.npoin)
            self.y = self._floats(f, self.npoin)
            self.data_start = f.tell()
            size = os.fstat(f.fileno()).st_size
        fs = self.float.itemsize
        self.frame_size = (8 + fs) + self.nvar * (8 + self.npoin * fs)
        self.nframes = (size - self.data_start) // self.frame_size  # an incomplete last frame is ignored
        self.times = np.empty(self.nframes)
        with open(path, "rb") as f:
            for i in range(self.nframes):
                f.seek(self.data_start + i * self.frame_size)
                self.times[i] = self._floats(f, 1)[0]

    def _record(self, f):
        n = struct.unpack(self.endian + "i", f.read(4))[0]
        data = f.read(n)
        tail = f.read(4)
        if len(data) != n or len(tail) != 4 or struct.unpack(self.endian + "i", tail)[0] != n:
            raise ValueError("truncated or corrupted Fortran record")
        return data

    def _ints(self, f, n):
        rec = self._record(f)
        if len(rec) != 4 * n:
            raise ValueError("unexpected record length %d (expected %d integers)" % (len(rec), n))
        return np.frombuffer(rec, dtype=self.endian + "i4").astype(int).tolist()

    def _floats(self, f, n):
        rec = self._record(f)
        if len(rec) == 4 * n and self.float.itemsize == 8:  # time stored in single precision
            return np.frombuffer(rec, dtype=self.endian + "f4").astype(float)
        return np.frombuffer(rec, dtype=self.float).astype(float)

    def frame(self, i):
        """Return the (nvar, npoin) values of frame i."""
        fs = self.float.itemsize
        out = np.empty((self.nvar, self.npoin))
        with open(self.path, "rb") as f:
            for v in range(self.nvar):
                f.seek(self.data_start + i * self.frame_size + (8 + fs) + v * (8 + self.npoin * fs) + 4)
                out[v] = np.frombuffer(f.read(self.npoin * fs), dtype=self.float)
        return out


RESULTS_KEYWORDS = ("RESULTS FILE", "FICHIER DES RESULTATS")


def cas_value(cas, keywords):
    """Value of the first of the keywords set in a steering file (.cas), or None.

    '/' starts a comment (outside quotes); the value may follow '=' or ':' and be
    on the next line; quotes around the value are removed.
    """
    with open(cas, encoding="latin-1") as f:
        text = "\n".join(re.sub(r"^((?:[^'\"/]|'[^']*'|\"[^\"]*\")*)/.*$", r"\1", line) for line in f)
    for kw in keywords:
        m = re.search(r"(?im)^[ \t]*" + re.escape(kw) + r"[ \t]*[=:]\s*('[^']*'|\"[^\"]*\"|[^\s;]+)", text)
        if m:
            return m.group(1).strip("'\"").strip()
    return None


def read_poi_file(path):
    poi = {}
    with open(path, encoding="latin-1") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or line[0] == "!":
                continue
            if "=" not in line:
                raise ValueError("%s: line without '=': %r" % (path, line))
            name, spec = line.split("=", 1)
            poi[name.strip()] = spec.strip()
    return poi


def _xy(s):
    x, y = s.split(",")
    return float(x), float(y)


def parse_spec(spec):
    """Return ('node', [index]) or ('points', [(x, y), ...]) for a POI spec."""
    spec = spec.replace(" ", "")
    parts = spec.split(":")
    if len(parts) == 1:
        if "," in spec:
            return "points", [_xy(spec)]
        return "node", [int(spec) - 1]
    if len(parts) == 3:
        (x0, y0), (x1, y1) = _xy(parts[0]), _xy(parts[2])
        if "," in parts[1]:  # grid x0,y0:nx,ny:x1,y1
            nx, ny = (int(n) for n in parts[1].split(","))
            xs = np.linspace(x0, x1, nx) if nx > 1 else np.array([x0])
            ys = np.linspace(y0, y1, ny) if ny > 1 else np.array([y0])
            return "points", [(x, y) for y in ys for x in xs]
        n = int(parts[1])  # line x0,y0:n:x1,y1
        t = np.linspace(0.0, 1.0, n) if n > 1 else np.array([0.0])
        return "points", [(x0 + ti * (x1 - x0), y0 + ti * (y1 - y0)) for ti in t]
    raise ValueError("bad POI spec %r (expected x,y | node | x0,y0:n:x1,y1 | x0,y0:nx,ny:x1,y1)" % spec)


def interpolators(slf, points, eps=1e-9):
    """Nodes (P, 3) and linear weights (P, 3) of the triangle containing each point (NaN outside)."""
    if slf.ndp != 3:
        raise ValueError("only 2D triangular meshes are supported (%d nodes per element)" % slf.ndp)
    xe, ye = slf.x[slf.ikle], slf.y[slf.ikle]
    det = (ye[:, 1] - ye[:, 2]) * (xe[:, 0] - xe[:, 2]) + (xe[:, 2] - xe[:, 1]) * (ye[:, 0] - ye[:, 2])
    nodes = np.zeros((len(points), 3), dtype=int)
    weights = np.full((len(points), 3), np.nan)
    for p, (x, y) in enumerate(points):
        l1 = ((ye[:, 1] - ye[:, 2]) * (x - xe[:, 2]) + (xe[:, 2] - xe[:, 1]) * (y - ye[:, 2])) / det
        l2 = ((ye[:, 2] - ye[:, 0]) * (x - xe[:, 2]) + (xe[:, 0] - xe[:, 2]) * (y - ye[:, 2])) / det
        l3 = 1.0 - l1 - l2
        inside = np.flatnonzero((l1 >= -eps) & (l2 >= -eps) & (l3 >= -eps))
        if inside.size:
            e = inside[0]
            nodes[p] = slf.ikle[e]
            weights[p] = (l1[e], l2[e], l3[e])
    return nodes, weights


def nearest_nodes(slf, points):
    """Nearest node of each point, as (nodes, weights) like interpolators()."""
    nodes = np.array([[np.argmin((slf.x - x) ** 2 + (slf.y - y) ** 2)] * 3 for x, y in points])
    return nodes, np.tile([1.0, 0.0, 0.0], (len(points), 1))


def extract(slf, poi, variables=None, method="linear"):
    """Return {csv_stem: 2D array} for all POI and variables (rows: frames).

    method: "linear" (interpolation in the containing triangle, NaN outside the
    mesh) or "nearest" (value of the nearest node, as the Java Funz plugin did).
    """
    names = var_names(slf)
    selected = [i for i, n in enumerate(names) if not variables or n in variables]
    plans = {}
    out = {"T": slf.times.reshape(-1, 1)}
    for name, spec in poi.items():
        kind, items = parse_spec(spec)
        if kind == "node":
            if not 0 <= items[0] < slf.npoin:
                raise ValueError("POI %s: node %d out of range 1..%d" % (name, items[0] + 1, slf.npoin))
            plans[name] = (np.array([[items[0]] * 3]), np.array([[1.0, 0.0, 0.0]]))
        else:
            nodes, weights = (nearest_nodes if method == "nearest" else interpolators)(slf, items)
            outside = np.isnan(weights[:, 0])
            if outside.any():
                print("warning: POI %s: %d point(s) outside the mesh (NaN)" % (name, outside.sum()), file=sys.stderr)
            plans[name] = (nodes, weights)
            if len(items) > 1:
                out["xy_" + name] = np.array(items)
    series = {(v, name): np.empty((slf.nframes, len(plan[0]))) for v in selected for name, plan in plans.items()}
    for i in range(slf.nframes):
        values = slf.frame(i)
        for v in selected:
            for name, (nodes, weights) in plans.items():
                series[(v, name)][i] = (values[v][nodes] * weights).sum(axis=1)
    for (v, name), a in series.items():
        out[names[v] + "_" + name] = a
    return out


def write_csv(path, a):
    with open(path, "w") as f:
        for row in np.atleast_2d(a):
            f.write(",".join(repr(float(v)) for v in row) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("-r", "--result", help="Serafin result file (.slf, .res)")
    src.add_argument("-c", "--cas", help="steering file giving the RESULTS FILE")
    ap.add_argument("poi", nargs="+", help=".poi file(s) and/or name=spec definitions")
    ap.add_argument("-o", "--outdir", help="output directory (default: the result file directory)")
    ap.add_argument("-v", "--vars", help="comma-separated short names of the variables to extract (default: all)")
    ap.add_argument("-m", "--method", choices=("linear", "nearest"), default="linear",
                    help="linear interpolation in the containing triangle (default), or nearest node value")
    args = ap.parse_args(argv)

    try:
        poi = {}
        for p in args.poi:
            if os.path.isfile(p):
                poi.update(read_poi_file(p))
            elif "=" in p:
                name, spec = p.split("=", 1)
                poi[name.strip()] = spec.strip()
            else:
                raise ValueError("%s: neither a POI file nor a name=spec definition" % p)
        if not poi:
            raise ValueError("no POI defined")
        for spec in poi.values():
            parse_spec(spec)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1

    if args.cas:
        try:
            res = cas_value(args.cas, RESULTS_KEYWORDS)
        except OSError as e:
            print("error: cannot read %s: %s" % (args.cas, e), file=sys.stderr)
            return 1
        if not res:
            print("error: no RESULTS FILE in %s" % args.cas, file=sys.stderr)
            return 1
        args.result = os.path.join(os.path.dirname(os.path.abspath(args.cas)), res)
    try:
        slf = Serafin(args.result)
    except (OSError, ValueError, struct.error) as e:
        print("error: cannot read %s: %s" % (args.result, e), file=sys.stderr)
        return 2
    print("%s: %d variables (%s), %d nodes, %d frames" % (
        args.result, slf.nvar, ", ".join(var_names(slf)), slf.npoin, slf.nframes))

    try:
        data = extract(slf, poi, args.vars.split(",") if args.vars else None, args.method)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.result))
    os.makedirs(outdir, exist_ok=True)
    for stem, a in data.items():
        write_csv(os.path.join(outdir, stem + ".csv"), a)
    print("wrote %d CSV files in %s" % (len(data), outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
