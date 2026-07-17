# Stop Guessing: A Smarter Way to Infer Time Frequencies in Climate Data

*A practical guide to robust frequency inference for climate time series.*

Time series are the backbone of climate science. Understanding the **temporal
resolution** (frequency) of your data is a vital first step in any automated
pipeline. In the Python ecosystem, `xarray` is the workhorse for this—but one
of the simplest-sounding tasks, figuring out the frequency of a time
coordinate, often breaks in practice.

---

## The Problem: Three Ways `xarray.infer_freq()` Returns `None`

`pandas` and `xarray` infer frequency by expecting perfectly regular,
standard-calendar timestamps. Real climate model output rarely satisfies all
three of those conditions at once.

### 1. Non-standard calendars

Climate models routinely use calendars that standard Python `datetime` cannot
represent—`noleap` (365 days every year), `360_day` (12 × 30 days), and
others. `xarray` delegates to `pandas` for inference, which doesn't understand
`cftime` objects at all:

```python
import cftime, xarray as xr
from pycmor.core.infer_freq import infer_frequency

times = [
    cftime.Datetime360Day(2000, m, 16) for m in range(1, 5)
]

print(xr.infer_freq(times))         # raises TypeError — cftime not supported
print(infer_frequency(times))       # 'M'
```

### 2. Unanchored (shifted) timestamps

Monthly means are often stamped mid-month rather than on the first or last day.
The spacing between timestamps is still ~30 days, but `xarray.infer_freq`
requires stamps to fall on a recognised anchor:

```python
import pandas as pd

# Monthly data stamped on the 6th of each month
times = pd.date_range("2000-01-01", periods=4, freq="MS") + pd.Timedelta(days=5)

print(xr.infer_freq(times))         # None
print(infer_frequency(times))       # 'M'
```

### 3. Missing steps or duplicates

A single missing month, or duplicate timestamps from accidentally concatenating
the same file twice, is enough to make `xarray.infer_freq` return `None`:

```python
# March is missing
times = pd.to_datetime(["2000-01-31", "2000-02-29", "2000-04-30"])

print(xr.infer_freq(times))         # None
print(infer_frequency(times))       # 'M'
```

---

## The Fix: `pycmor.core.infer_freq`

Rather than requiring perfectly regular, standard-calendar timestamps,
`infer_frequency` works from the actual shape of the data:

- **Compute deltas** between all consecutive time points.
- **Take the median delta** — this smooths over gaps, duplicates, and small
  misalignments without rejecting the whole series.
- **Convert all timestamps** (including `cftime`) to a comparable numerical
  format before doing any arithmetic.

The result is a function that handles all three failure modes above, across any
calendar — and instead of a silent `None`, it returns an actionable answer.

---

## End-to-End: Detecting Issues After File Concatenation

Combining NetCDF files from different sources is one of the most common sources
of subtle time-axis corruption — overlapping chunks, a missing month,
misaligned calendars. This is where a silent `None` from `xarray.infer_freq`
is most dangerous: you don't know if your data is clean until something
downstream breaks.

`infer_frequency` gives you a single call to catch all of it upfront:

```python
import numpy as np
import pandas as pd
import xarray as xr
from pycmor.core.infer_freq import infer_frequency

# Simulate two NetCDF files: Jan–Jun and Jul–Dec 2000.
# File 2 has a gap: July 15 is missing.
file1_times = pd.date_range("2000-01-01", "2000-06-30", freq="D")

file2_part1 = pd.date_range("2000-07-01", "2000-07-14", freq="D")
file2_part2 = pd.date_range("2000-07-16", "2000-12-31", freq="D")
file2_times = file2_part1.append(file2_part2)

# Check each file individually before combining
for i, times in enumerate([file1_times, file2_times], 1):
    result = infer_frequency(times, return_metadata=True, strict=True)
    print(f"File {i}: status={result.status!r}, is_exact={result.is_exact}")

# File 1: status='valid', is_exact=True
# File 2: status='missing_steps', is_exact=False  ← caught before concat
```

Catching problems per-file first is preferable to discovering them after
combining hundreds of files. But `infer_frequency` works equally well on the
combined time axis:

```python
# Use np.concatenate (not .union) to preserve duplicates and ordering
combined_times = pd.DatetimeIndex(
    np.concatenate([file1_times, file2_times])
)

result = infer_frequency(combined_times, return_metadata=True, strict=True)
print(f"Combined: status={result.status!r}, frequency={result.frequency!r}")
# Combined: status='missing_steps', frequency='D'
```

The call costs microseconds and can be inserted as an assertion at any
pipeline stage:

```python
def load_and_validate(paths):
    ds = xr.open_mfdataset(paths, combine="by_coords")
    result = infer_frequency(ds.time, return_metadata=True, strict=True)
    if result.status != "valid" or not result.is_exact:
        raise ValueError(
            f"Time axis issue after combining {len(paths)} files: "
            f"status={result.status!r}, frequency={result.frequency!r}"
        )
    return ds
```

---

## Rich Diagnostics Instead of Silent Failure

Every `return_metadata=True` call returns a `FrequencyResult` object. Here is
what each field tells you:

```python
from pycmor.core.infer_freq import infer_frequency

times = ["2000-01-01", "2000-02-01", "2000-02-28", "2000-04-01"]

result = infer_frequency(times, return_metadata=True, strict=True)
# strict=True tightens classification: it re-checks spacing and expected step
# count, flipping status to 'irregular' or 'missing_steps' (and is_exact=False)
# whenever those checks fail — it never raises on its own.
```

```python
FrequencyResult(
  frequency='M',
  delta_days=27.0,
  step=1,
  is_exact=False,
  status='irregular'
)
```

| Field | Description |
|-------|-------------|
| `frequency` | Inferred frequency string (`'D'`, `'M'`, `'MS'`, etc.) |
| `delta_days` | Median spacing between time steps, in days |
| `step` | Multiplier (e.g. `step=3` with `frequency='M'` means quarterly) |
| `is_exact` | `True` only if every spacing is identical |
| `status` | `'valid'`, `'irregular'`, `'missing_steps'`, `'no_match'`, `'too_short'`, or `'invalid_input: ...'` |

**How to interpret `status`:**

- `valid` + `is_exact=True` → safe for resampling and analysis
- `irregular` → underlying frequency detectable but spacing is inconsistent
- `missing_steps` → gaps present; consider filling before analysis
- `no_match` → no frequency could be matched, even with relaxed tolerance
- `too_short` → fewer than two points; cannot determine frequency
- `invalid_input: ...` → timestamps couldn't be converted (message has details)

---

## Takeaway

`pycmor.core.infer_freq` addresses the three concrete ways `xarray.infer_freq`
silently fails on real climate data:

- non-standard calendars → handled via cftime-aware delta computation
- unanchored timestamps → handled via median-based inference
- gaps and duplicates → surfaced via `FrequencyResult.status`

The diagnostics turn a silent `None` into an actionable signal. Insert one call
after loading or concatenating files and you have an early-warning system for
the most common class of time-axis corruption.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/esm-tools/pycmor/HEAD?labpath=blog%2Finfer_frequency.ipynb)

---

## Project Repository

- GitHub: [esm-tools/pycmor](https://github.com/esm-tools/pycmor)
- PyPI: [pycmor](https://pypi.org/project/pycmor/)

---

## Authors

This work was developed by the High Performance Computing and Data Processing
group at the Alfred Wegener Institute for Polar and Marine Research (AWI),
Bremerhaven, Germany.

- Pavan Kumar Siligam (AWI) — [ORCID: 0009-0003-8054-7021](https://orcid.org/0009-0003-8054-7021)
- Paul Gierz (AWI) — [ORCID: 0000-0002-4512-087X](https://orcid.org/0000-0002-4512-087X)
- Miguel Andrés-Martínez (AWI) — [ORCID: 0000-0002-1525-5546](https://orcid.org/0000-0002-1525-5546)
