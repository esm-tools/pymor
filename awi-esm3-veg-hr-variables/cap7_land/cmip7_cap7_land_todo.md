# CMIP7 CAP7 Land Variables — TODO

Variables deferred from core_land that cannot be produced from IFS/OIFS output alone.
These require LPJ-GUESS dynamic vegetation output or external datasets.

## From core_land CSVs (deferred)

### Need LPJ-GUESS output

- [ ] **evspsblsoi** — Water Evaporation from Soil (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblsoi.tavg-u-hxy-lnd.mon.glb`
  - IFS `e` is total evaporation (soil + canopy + sublimation), not partitioned
  - LPJ-GUESS should provide soil evaporation separately
  - **OIFS source option**: Bare soil evaporation is computed internally as `PDHWLS(:,1,9)` / `D1SW1JBG` in `srfwexc_mod.F90`. Would need new GRIB field registration in `ptrgfu.F90` + `sucfu.F90` + `cpg_dia.F90` to expose via XIOS

- [ ] **evspsblveg** — Evaporation from Canopy (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblveg.tavg-u-hxy-lnd.mon.glb`
  - Same issue: IFS doesn't partition evaporation by source
  - LPJ-GUESS should provide canopy evaporation (interception loss)
  - **OIFS source option**: Transpiration is already a GRIB field (`SURFTRANSPIRATIO` / GFP `CTP`) — can be requested via XIOS without source changes. Interception evaporation is `PDHIIS(:,4)` / `D1SWLJQ` in `upddiag.F90` — would need GRIB registration to expose. CMIP7 evspsblveg = interception + transpiration, so both components are needed

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

- [ ] **mrfso** — Soil Frozen Water Content (`kg m-2`, LImon)
  - compound_name: `landIce.mrfso.tavg-u-hxy-lnd.mon.glb`
  - IFS HTESSEL tracks total soil moisture but liquid/frozen partitioning is internal
  - **OIFS source option**: Frozen soil water per layer is computed as `PDHWLS(:,:,2)` in `srfwexc_mod.F90` (frozen fraction from soil temperature). Liquid water = `D1SWAFR` in `upddiag.F90` line 436. Would need new GRIB field registration to expose sum of frozen water across 4 layers via XIOS

## Additional CAP7-specific land variables

(To be populated when CAP7 land CSV is available)
