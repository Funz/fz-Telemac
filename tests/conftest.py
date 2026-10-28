import struct
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".fz" / "calculators"))


def write_serafin(path, x, y, ikle, frames, names, times, endian=">", double=False):
    """Write a 2D Serafin file: frames[i][v] = values of variable v at frame i."""
    fdt = np.dtype(endian + ("f8" if double else "f4"))

    def rec(f, data):
        f.write(struct.pack(endian + "i", len(data)) + data + struct.pack(endian + "i", len(data)))

    def ints(a):
        return np.asarray(a, dtype=endian + "i4").tobytes()

    with open(path, "wb") as f:
        rec(f, ("synthetic".ljust(72) + ("SERAFIND" if double else "SERAFIN ")).encode())
        rec(f, ints([len(names), 0]))
        for n in names:
            rec(f, n.ljust(32).encode("latin-1"))
        rec(f, ints([1, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
        rec(f, ints([len(ikle), len(x), 3, 1]))
        rec(f, ints(np.asarray(ikle) + 1))
        rec(f, ints(np.zeros(len(x))))
        rec(f, np.asarray(x, dtype=fdt).tobytes())
        rec(f, np.asarray(y, dtype=fdt).tobytes())
        for t, frame in zip(times, frames):
            rec(f, np.asarray([t], dtype=fdt).tobytes())
            for values in frame:
                rec(f, np.asarray(values, dtype=fdt).tobytes())


@pytest.fixture
def square_mesh():
    """Unit square [0,10]x[0,10] split in 2 triangles."""
    x = np.array([0.0, 10.0, 10.0, 0.0])
    y = np.array([0.0, 0.0, 10.0, 10.0])
    ikle = np.array([[0, 1, 2], [0, 2, 3]])
    return x, y, ikle
