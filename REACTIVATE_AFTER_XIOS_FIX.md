# Rules to reactivate once XIOS writes the new mrsol streams

Three rules are deactivated in the AWI-ESM3-veg-HR recipes because the model
output they need does not exist in the current HR run. They are commented out
in place, so reactivating is uncommenting plus repointing the input pattern.

The matching XIOS change is in `esm_tools`:
`namelists/oifs/48r1/xios/cmip7/file_def_oifs_cmip7_spinup.xml.j2`

Applies to any run started after that file_def lands, LR included.

## Why they were deactivated

A single 3-hourly stream (`atmos_3h_land_mrsol`, `operation="instant"`, carrying
the **100 cm** field) was feeding three DReq entries that disagree on both depth
and temporal shape. Two consequences:

- `tavg-d100cm` received instantaneous samples, so it could not be a mean.
- Both `d10cm` entries silently read the 100 cm field, publishing 1 m soil
  moisture as 10 cm.

The depth error was confirmed on cli108 output: 3hr `d10cm` mean 72.6 kg m-2
against 6.9 for the genuinely-10 cm monthly rule, a 10.5x ratio matching the
1.00 m / 0.10 m depth ratio. It is a wrong-values problem, not a metadata one,
and no QC check catches it.

## The three rules

| Rule | File | DReq entry | New stream |
|---|---|---|---|
| `mrsol_3hr_100cm` | `veg_land/cmip7_awiesm3-veg-hr_land.yaml` | `land.mrsol.tavg-d100cm-hxy-lnd.3hr.glb` | `atmos_3h_land_mrsol100_avg` |
| `mrsol_3hr_10cm` | `veg_land/cmip7_awiesm3-veg-hr_land.yaml` | `land.mrsol.tpt-d10cm-hxy-lnd.3hr.glb` | `atmos_3h_land_mrsol10_inst` |
| `mrsol_day_10cm` | `cap7_land/cmip7_awiesm3-veg-hr_cap7_land.yaml` | `land.mrsol.tavg-d10cm-hxy-lnd.day.glb` | `atmos_day_land_mrsol10_avg` |

Input patterns to use when uncommenting:

- `atmos_3h_land_mrsol100_avg_mrsol_.*\.nc`
- `atmos_3h_land_mrsol10_inst_mrsol_.*\.nc`
- `atmos_day_land_mrsol10_avg_mrsol_.*\.nc`

Confirm the exact filenames against the first year of output before trusting
these: XIOS composes them from the `<file name=...>` plus the field name under
`timeseries="only"`, and the composition has not yet been observed on disk.

## Checks before trusting the reactivated output

- **Depth.** `d10cm` values should be roughly a tenth of `d100cm`. If a 3-hourly
  `d10cm` file reports means near 70 kg m-2 rather than near 7, it is reading the
  100 cm field again.
- **Operation.** `ncdump -h` the source; `online_operation` must be `average` for
  the two `tavg` entries and `instant` for the `tpt` one.
- **Timestamps.** An averaged 3h stream should be stamped at window midpoints
  (01:30, 04:30, ...). Boundary stamps (03:00, 06:00, ...) with a trailing sample
  in the following year mean it is still `instant`.

## Not affected

These stay enabled and read correct sources:

- `mrsol` (`core_land`) `tavg-d10cm` monthly, reads `atmos_mon_land`
- `mrsol_mon` (`cap7_land`) `tavg-sl` monthly, reads LPJ-GUESS `.out`
- `mrsolLut_mon` (`veg_land`), reads LPJ-GUESS `.out`
- `tslsi_3hr`, already `tpt` and correctly fed by an `instant` stream

## Open question

Only `mrsol` was audited this way, because the DKRZ review pointed at it. Other
variables sharing one XIOS stream across several DReq entries could have the same
class of problem, and it is invisible to QC. A sweep comparing each rule's
`compound_name` against the `operation` and field definition of the stream it
reads would be worth doing before publication.
