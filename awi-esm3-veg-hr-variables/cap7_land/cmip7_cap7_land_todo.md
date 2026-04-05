# CMIP7 CAP7 Land Variables — TODO

Variables deferred from core_land that cannot be produced from IFS/OIFS output alone.
These require LPJ-GUESS dynamic vegetation output or external datasets.

## From core_land CSVs (deferred)

### Need LPJ-GUESS output

- [ ] **evspsblsoi** — Water Evaporation from Soil (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblsoi.tavg-u-hxy-lnd.mon.glb`
  - IFS `e` is total evaporation (soil + canopy + sublimation), not partitioned
  - LPJ-GUESS should provide soil evaporation separately

- [ ] **evspsblveg** — Evaporation from Canopy (`kg m-2 s-1`, Lmon)
  - compound_name: `land.evspsblveg.tavg-u-hxy-lnd.mon.glb`
  - Same issue: IFS doesn't partition evaporation by source
  - LPJ-GUESS should provide canopy evaporation (interception loss)

- [ ] **rootd** — Maximum Root Depth (`m`, fx)
  - compound_name: `land.rootd.ti-u-hxy-lnd.fx.glb`
  - IFS HTESSEL has fixed total depth 2.89m, no spatially varying root depth
  - LPJ-GUESS has PFT-dependent root depth profiles

### Need external data / research

- [ ] **mrsofc** — Capacity of Soil to Store Water / Field Capacity (`kg m-2`, fx)
  - compound_name: `land.mrsofc.ti-u-hxy-lnd.fx.glb`
  - Depends on IFS soil type classification + HTESSEL lookup tables
  - Could be derived from IFS initial condition files (soil type map)
  - Alternatively, LPJ-GUESS may override with its own soil parameters

- [ ] **sftgif** — Land Ice Area Percentage (`%`, fx)
  - compound_name: `land.sftgif.ti-u-hxy-u.fx.glb`
  - Not a standard IFS prognostic/diagnostic field
  - Needs external glacier/ice sheet mask (e.g., from GLIMS, RGI, or ESM initial conditions)

- [ ] **mrfso** — Soil Frozen Water Content (`kg m-2`, LImon)
  - compound_name: `landIce.mrfso.tavg-u-hxy-lnd.mon.glb`
  - IFS HTESSEL tracks total soil moisture but liquid/frozen partitioning is internal
  - May need dedicated OIFS diagnostic output, or could be approximated from soil temperature + total moisture using freeze curve
  - Research needed: check if HTESSEL outputs frozen fraction in any form

## Additional CAP7-specific land variables

(To be populated when CAP7 land CSV is available)
