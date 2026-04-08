# CMIP7 CAP7 Land Variables — TODO

Variables deferred from core_land that cannot be produced from IFS/OIFS output alone.
These require LPJ-GUESS dynamic vegetation output or external datasets.

## From core_land CSVs (deferred)

### From LPJ-GUESS output (now implemented)

- [x] **evspsblsoi** — Water Evaporation from Soil (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblsoi.tavg-u-hxy-lnd.mon.glb`
  - From LPJ-GUESS `evspsblsoi_monthly.out` (Jan..Dec format)
  - IFS `e` is total evaporation (not partitioned), but LPJ-GUESS provides soil evaporation separately

- [x] **evspsblveg** — Evaporation from Canopy (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblveg.tavg-u-hxy-lnd.mon.glb`
  - From LPJ-GUESS `evspsblveg_monthly.out` (Jan..Dec format)
  - LPJ-GUESS provides canopy evaporation (interception loss)

- [ ] **rootd** — Maximum Root Depth (`m`, fx)
  - compound_name: `land.rootd.ti-u-hxy-lnd.fx.glb`
  - IFS HTESSEL has fixed total depth 2.89m, no spatially varying root depth
  - LPJ-GUESS has PFT-dependent root depth profiles
  - **No source change needed**: HTESSEL defines per-vegetation-type root fraction profiles in `srfrootfr_mod.F90` using Zeng et al. (1998) exponential distribution. Effective root depth can be computed offline from `tvl`/`tvh` vegetation type fields + lookup table of root profile parameters

### Need external data / research

- [ ] **mrsofc** — Capacity of Soil to Store Water / Field Capacity (`kg m-2`, fx)
  - compound_name: `land.mrsofc.ti-u-hxy-lnd.fx.glb`
  - Depends on IFS soil type classification + HTESSEL lookup tables
  - Could be derived from IFS initial condition files (soil type map)
  - Alternatively, LPJ-GUESS may override with its own soil parameters
  - **No source change needed**: Field capacity `RWCAP`/`RWCAPM` is computed in `sussoil_mod.F90` from Van Genuchten parameters per soil type. Can derive offline from IFS soil type initial condition field + HTESSEL lookup tables

- [ ] **sftgif** — Land Ice Area Percentage (`%`, fx)
  - compound_name: `land.sftgif.ti-u-hxy-u.fx.glb`
  - Not a standard IFS prognostic/diagnostic field
  - Needs external glacier/ice sheet mask (e.g., from GLIMS, RGI, or ESM initial conditions)
  - **No source change needed**: IFS vegetation type 12 = "Ice Caps and Glaciers" (BATS classification in `srfrootfr_mod.F90`). Can derive sftgif from `tvl`/`tvh` fields: where dominant vegetation type = 12, set glacier fraction accordingly

- [x] **mrfso** — Soil Frozen Water Content (`kg m-2`, LImon)
  - compound_name: `landIce.mrfso.tavg-u-hxy-lnd.mon.glb`
  - From LPJ-GUESS `mrfso_monthly.out` (Jan..Dec format)
  - LPJ-GUESS tracks frozen soil water content directly

## Additional CAP7-specific land variables

(To be populated when CAP7 land CSV is available)
