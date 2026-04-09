# CMIP7 LRCS Ocean Variables — Rule Implementation TODO

Variables from `cmip7_LRCSextra_variables_ocean.csv` for AWI-ESM3-VEG-HR.
Excludes variables already in core_ocean rules (tos, sos, zos, so, thetao, uo, vo, wo,
hfds, mlotst, tauuo, tauvo, absscint, umo, vmo, wmo, zostoga, areacello, deptho, sftof,
thkcello, masscello).

## Legend
- [x] done — rule written
- [ ] todo — feasible, not yet implemented
- [~] skipped — not applicable or not possible with this model

---

## Monthly 2D surface (Omon) — feasible from existing output

- [x] **tob** — Sea Water Potential Temperature at Sea Floor (`degC`, mon)
  Rule written: bottom_extract_pipeline from temp.fesom
- [x] **sob** — Sea Water Salinity at Sea Floor (`1E-03`, mon)
  Rule written: bottom_extract_pipeline from salt.fesom
- [x] **pbo** — Sea Water Pressure at Sea Floor (`Pa`, mon)
  Rule written: direct mapping from ldiag_cmor pbo.fesom
- [x] **pso** — Sea Water Pressure at Sea Water Surface (`Pa`, mon)
  Rule written: surface_pressure_pipeline (rho_0 * g * ssh)
- [x] **tossq** — Square of Sea Surface Temperature (`degC2`, mon)
  Rule written: square_pipeline from sst.fesom
- [x] **sossq** — Square of Sea Surface Salinity (`1E-06`, mon)
  Rule written: square_pipeline from sss.fesom
- [x] **zossq** — Square of Sea Surface Height (`m2`, mon)
  Rule written: square_pipeline from ssh.fesom
- [x] **mlotstsq** — Square of Ocean Mixed Layer Thickness (`m2`, mon)
  Rule written: square_pipeline from MLD3.fesom
- [x] **wfo** — Water Flux into Sea Water (`kg m-2 s-1`, mon)
  Rule written: scale_pipeline (fw × 1000)
- [x] **evspsbl** — Evaporation Where Ice Free Ocean (`kg m-2 s-1`, mon)
  Rule written: scale_pipeline (evap × 1000). Needs 'evap' added to namelist.io. Note: may need ice-free masking.
- [ ] **sfriver** — Salt Flux from Rivers (`kg m-2 s-1`, mon)
  BLOCKED: no river salt flux diagnostic in FESOM2
- [x] **vsf** — Virtual Salt Flux into Sea Water (`kg m-2 s-1`, mon)
  Rule written: direct mapping from virtsalt.fesom (already in namelist.io)
- [x] **vsfcorr** — Virtual Salt Flux Correction (`kg m-2 s-1`, mon)
  Rule written: direct mapping from relaxsalt.fesom. Needs 'relaxsalt' added to namelist.io. Verify unit conversion.
- [ ] **vsfevap** — Virtual Salt Flux Due to Evaporation (`kg m-2 s-1`, mon)
  BLOCKED: FESOM does not split virtual salt flux by component
- [ ] **vsfpr** — Virtual Salt Flux Due to Rainfall (`kg m-2 s-1`, mon)
  BLOCKED: FESOM does not split virtual salt flux by component
- [ ] **vsfriver** — Virtual Salt Flux from Rivers (`kg m-2 s-1`, mon)
  BLOCKED: FESOM does not split virtual salt flux by component
- [ ] **wfcorr** — Water Flux Correction (`kg m-2 s-1`, mon)
  BLOCKED: no water flux correction in standard FESOM2 config
- [x] **msftbarot** — Ocean Barotropic Mass Streamfunction (`kg s-1`, mon)
  DONE: geostrophic SSH approximation psi = rho_0*g*H/f*eta (compute_msftbarot in custom_steps.py,
  msftbarot_pipeline + rule in cmip7_awiesm3-veg-hr_lrcs_ocean.yaml). NaN in equatorial band |f|<1e-5.

## Monthly 2D surface (Omon) — atmosphere-coupled fluxes

- [ ] **hfevapds** — Heat Flux Due to Evaporation (`W m-2`, mon)
  BLOCKED: requires atmosphere-side heat flux decomposition
- [ ] **hfrainds** — Heat Flux Due to Rainfall (`W m-2`, mon)
  BLOCKED: requires atmosphere-side heat flux decomposition
- [ ] **rsds** — Surface Downwelling Shortwave over Ice-Free Ocean (`W m-2`, mon)
  Available: swr.fesom [W/m²] — but this is the total, not ice-free-only component
- [ ] **rsus** — Surface Upwelling Shortwave over Ice-Free Ocean (`W m-2`, mon)
  BLOCKED: FESOM does not output reflected shortwave separately

## Monthly 2D — ice/land freshwater interactions

- [ ] **ficeberg** — Water Flux from Icebergs (`kg m-2 s-1`, mon)
  BLOCKED: requires use_icebergs=.true. (not enabled)
- [ ] **flandice** — Water Flux from Land Ice (`kg m-2 s-1`, mon)
  Possible: landice.fesom if use_landice_water=.true.; check config
- [ ] **hfibthermds** — Heat Flux from Iceberg Thermodynamics (`W m-2`, mon)
  BLOCKED: requires use_icebergs=.true.
- [ ] **hfrunoffds** — Heat Flux from Runoff (`W m-2`, mon)
  BLOCKED: requires runoff temperature, not output by FESOM
- [ ] **hfsnthermds** — Heat Flux from Snow Thermodynamics (`W m-2`, mon)
  BLOCKED: requires separate snow thermodynamic heat flux diagnostic
- [ ] **hfgeou** — Upward Geothermal Heat Flux (`W m-2`, mon)
  BLOCKED: not in FESOM output or config (same as Ofx version)

## Monthly 3D (Omon) — feasible from existing output

- [x] **obvfsq** — Square of Brunt-Vaisala Frequency (`s-2`, mon)
  Rule written: direct mapping from N2.fesom

## Monthly global mean scalars (Omon)

- [x] **tos_ga** — Global Average SST (`degC`, mon)
  Rule written: direct mapping from thetaoga.fesom (ldiag_cmor)
- [x] **sos_ga** — Global Average SSS (`1E-03`, mon)
  Rule written: direct mapping from soga.fesom (ldiag_cmor)
- [x] **thetao_ga** — Global Average Potential Temperature (`degC`, mon, per level)
  Rule written: using thetaoga scalar (per-level profile needs volume-weighted avg)
- [x] **so_ga** — Global Mean Salinity (`1E-03`, mon, per level)
  Rule written: using soga scalar (per-level profile needs volume-weighted avg)
- [x] **masso** — Sea Water Mass (`kg`, mon)
  Rule written: scale_pipeline (volo × rho_0=1025)
- [x] **volo** — Sea Water Volume (`m3`, mon)
  Rule written: direct mapping from volo.fesom (ldiag_cmor)

## Monthly depth-integrated (Omon, oplayer4)

- [x] **scint** — Depth-integrated practical salinity as salt content (`kg m-2`, mon)
  Rule written: ocean_vertical_integration_pipeline from salt.fesom
- [ ] **pfscint** — Depth-integrated preformed salinity (`kg m-2`, mon)
  BLOCKED: no preformed salinity tracer in FESOM
- [x] **phcint** — Integrated Ocean Heat Content from Potential Temperature (`J m-2`, mon)
  Rule written: ocean_vertical_integration_pipeline from temp.fesom (needs rho_0*cp scaling)
- [ ] **chcint** — Integrated Conservative Temperature as Heat Content (`J m-2`, mon)
  BLOCKED: FESOM uses potential temperature, not conservative

## Monthly — transport and overturning

- [ ] **sfx** — 3D Ocean Salt Mass X Transport (`kg s-1`, mon, 3D)
  Compute: unod × salt × cell cross-section area; complex
- [ ] **sfy** — 3D Ocean Salt Mass Y Transport (`kg s-1`, mon, 3D)
  Compute: vnod × salt × cell cross-section area; complex
- [ ] **msftmmpa** — MOC Due to Parameterized Mesoscale Advection (`kg s-1`, mon)
  Possible: compute from bolus_u/bolus_v (GM velocities in namelist.io); needs basin masks
- [ ] **msftmsmpa** — MOC Due to Parameterized Submesoscale Advection (`kg s-1`, mon)
  BLOCKED: no submesoscale parameterization output
- [ ] **msftypa** — Ocean Y Overturning Due to Mesoscale (`kg s-1`, mon)
  BLOCKED: needs structured grid or regridding + basin masks
- [ ] **msfty** — Ocean Y Overturning Mass Streamfunction (`kg s-1`, mon)
  BLOCKED: needs structured grid or regridding + basin masks
- [ ] **msftm** — Meridional Overturning in Density Space (`kg s-1`, mon)
  Possible: ldiag_dMOC=.true. enabled, outputs dMOC; needs post-processing to match CMIP format

## Monthly — basin-zonal heat/salt transport

- [ ] **htovgyre** — Northward Heat Transport Due to Gyre (`W`, mon)
  BLOCKED: needs basin masks + decomposition into gyre/overturning
- [ ] **htovovrt** — Northward Heat Transport Due to Overturning (`W`, mon)
  BLOCKED: needs basin masks + decomposition
- [ ] **hfbasinpadv** — Heat Transport Due to Parameterized Eddy Advection (`W`, mon)
  BLOCKED: needs basin masks + GM decomposition
- [ ] **hfbasinpmadv** — Heat Transport Due to Mesoscale Advection (`W`, mon)
  BLOCKED: needs basin masks
- [ ] **hfbasinpmdiff** — Heat Transport Due to Mesoscale Diffusion (`W`, mon)
  BLOCKED: needs basin masks
- [ ] **hfbasinpsmadv** — Heat Transport Due to Submesoscale Advection (`W`, mon)
  BLOCKED: no submesoscale param
- [ ] **sltbasin** — Northward Salt Transport (`kg s-1`, mon)
  BLOCKED: needs basin masks
- [ ] **sltovgyre** — Salt Transport Due to Gyre (`kg s-1`, mon)
  BLOCKED: needs basin masks
- [ ] **sltovovrt** — Salt Transport Due to Overturning (`kg s-1`, mon)
  BLOCKED: needs basin masks

## Monthly — cross-line transports

- [ ] **hfacrossline** — Ocean Heat Transport Across Lines (`W`, mon)
  BLOCKED: requires predefined ocean transect lines (oline dimension)
- [ ] **sfacrossline** — Ocean Salt Transport Across Lines (`W`, mon)
  BLOCKED: requires predefined ocean transect lines
- [ ] **mfo** — Sea Water Transport Across Lines (`kg s-1`, mon)
  BLOCKED: requires predefined ocean transect lines

## Fixed frequency (Ofx) — grid cell dimensions

- [ ] **dxto** — Cell Length X at t-points (`m`, fx)
  BLOCKED: unstructured mesh — no dx/dy concept (would need Voronoi edge lengths)
- [ ] **dyto** — Cell Length Y at t-points (`m`, fx)
  BLOCKED: unstructured mesh
- [ ] **dxuo** — Cell Length X at u-points (`m`, fx)
  BLOCKED: unstructured mesh
- [ ] **dyuo** — Cell Length Y at u-points (`m`, fx)
  BLOCKED: unstructured mesh
- [ ] **dxvo** — Cell Length X at v-points (`m`, fx)
  BLOCKED: unstructured mesh
- [ ] **dyvo** — Cell Length Y at v-points (`m`, fx)
  BLOCKED: unstructured mesh
- [x] **volcello** — Ocean Grid-Cell Volume (`m3`, fx/yr/dec)
  Rule written: volcello_fx_pipeline (cell_area × layer_thickness from mesh); volcello_dec via volcello_time_pipeline

## Daily (Oday)

- [x] **mlotst_day** — Ocean Mixed Layer Thickness (`m`, day)
  Rule written: direct mapping from daily MLD3. Needs daily 'MLD3' added to namelist.io.
- [ ] **thetao200_day** — Potential Temp top 200m (`degC`, day)
  BLOCKED: no daily 3D output feasible; and needs op20bar layer extraction
- [x] **uos** — Daily Surface X Velocity (`m s-1`, day)
  Rule written: surface_extract_pipeline from daily unod. Needs daily 'unod' in namelist.io (WARNING: full 3D, expensive).
- [x] **vos** — Daily Surface Y Velocity (`m s-1`, day)
  Rule written: surface_extract_pipeline from daily vnod. Needs daily 'vnod' in namelist.io (WARNING: full 3D, expensive).
- [ ] **hfx** — Vertically Integrated Heat X Transport (`W`, day)
  BLOCKED: requires online computation (temp × u × dz integrated), too expensive daily
- [ ] **hfy** — Vertically Integrated Heat Y Transport (`W`, day)
  BLOCKED: same as hfx

## Decadal (Odec)

- [x] **thetao_dec** — Potential Temperature (`degC`, dec, 3D)
  Rule written: DefaultPipeline from temp.fesom (needs 10-yr input pattern)
- [x] **so_dec** — Salinity (`1E-03`, dec, 3D)
  Rule written: DefaultPipeline from salt.fesom
- [x] **tauuo_dec** — Surface X Stress (`N m-2`, dec)
  Rule written: DefaultPipeline from tx_sur.fesom
- [x] **tauvo_dec** — Surface Y Stress (`N m-2`, dec)
  Rule written: DefaultPipeline from ty_sur.fesom
- [x] **thkcello_dec** — Cell Thickness (`m`, dec, 3D)
  Rule written: DefaultPipeline from hnode.fesom
- [x] **masscello_dec** — Cell Mass per Area (`kg m-2`, dec, 3D)
  Rule written: scale_pipeline (hnode × rho_0=1025)
- [x] **volcello_dec** — Cell Volume (`m3`, dec, 3D)
  Rule written: volcello_time_pipeline (hnode × cell_area)
- [x] **masso_dec** — Sea Water Mass (`kg`, dec, scalar)
  Rule written: scale_pipeline (volo × rho_0)
- [x] **volo_dec** — Sea Water Volume (`m3`, dec, scalar)
  Rule written: DefaultPipeline from volo.fesom
- [ ] **bigthetao_dec** — Conservative Temperature (`degC`, dec, 3D)
  [~] SKIPPED: FESOM uses potential temperature

## Yearly tendency terms (Oyr) — require online diagnostics

- [x] **opottemptend** — Temperature Tendency (`W m-2`, yr, 3D)
  Rule written: direct mapping from opottemptend.fesom (ldiag_cmor)
- [x] **opottempdiff** — Temp Tendency from Dianeutral Mixing (`W m-2`, yr)
  FESOM2 source modified: computed as total - advection in gen_modules_cmor_diag.F90
- [~] **opottemppadvect** — Temp Tendency from Eddy Advection (`W m-2`, yr)
  SKIPPED: zero field (fer_gm=.false., no GM parameterization active)
- [~] **opottemppmdiff** — Temp Tendency from Mesoscale Diffusion (`W m-2`, yr)
  SKIPPED: zero field (fer_gm=.false.)
- [~] **opottemppsmadvect** — Temp Tendency from Submesoscale Advection (`W m-2`, yr)
  SKIPPED: zero field (no submesoscale parameterization)
- [x] **opottemprmadvect** — Temp Tendency from Residual Mean Advection (`W m-2`, yr)
  FESOM2 source modified: saved from del_ttf advection snapshot in gen_modules_cmor_diag.F90
- [~] **ocontemptend** — Conservative Temp Tendency (`W m-2`, yr) — SKIPPED: not conservative temp
- [~] **ocontempdiff** — same family — SKIPPED
- [~] **ocontemppadvect** — SKIPPED
- [~] **ocontemppmdiff** — SKIPPED
- [~] **ocontemppsmadvect** — SKIPPED
- [~] **ocontemprmadvect** — SKIPPED
- [x] **osalttend** — Salinity Tendency (`kg m-2 s-1`, yr, 3D)
  FESOM2 source modified: computed in gen_modules_cmor_diag.F90 (mirrors opottemptend)
- [x] **osaltdiff** — Salt Tendency from Dianeutral Mixing (`kg m-2 s-1`, yr)
  FESOM2 source modified: computed as total - advection in gen_modules_cmor_diag.F90
- [~] **osaltpadvect** — Salt Tendency from Eddy Advection (`kg m-2 s-1`, yr)
  SKIPPED: zero field (fer_gm=.false.)
- [~] **osaltpmdiff** — Salt Tendency from Mesoscale Diffusion (`kg m-2 s-1`, yr)
  SKIPPED: zero field (fer_gm=.false.)
- [~] **osaltpsmadvect** — Salt Tendency from Submesoscale (`kg m-2 s-1`, mon/yr)
  SKIPPED: zero field (no submesoscale parameterization)
- [x] **osaltrmadvect** — Salt Tendency from Residual Mean (`kg m-2 s-1`, yr)
  FESOM2 source modified: saved from del_ttf advection snapshot in gen_modules_cmor_diag.F90

## Yearly integrated fields (Oyr)

- [x] **opottempmint** — Depth Integral of rho×theta (`degC kg m-2`, yr)
  Rule written: ocean_vertical_integration_pipeline from temp.fesom (needs rho_0 post-multiply)
- [ ] **ocontempmint** — same for conservative temp — SKIPPED
- [x] **somint** — Depth Integral of rho×S (`g m-2`, yr)
  Rule written: ocean_vertical_integration_pipeline from salt.fesom (needs rho_0*1000 post-multiply)

## Yearly mixing/diffusivity (Oyr)

- [x] **difvho** — Vertical Heat Diffusivity (`m2 s-1`, yr, 3D)
  Rule written: direct mapping from Kv.fesom (same Kv for heat and salt in FESOM)
- [x] **difvso** — Vertical Salt Diffusivity (`m2 s-1`, yr, 3D)
  Rule written: direct mapping from Kv.fesom (same as difvho)
- [x] **difmxylo** — Momentum XY Laplacian Diffusivity (`m2 s-1`, yr, 3D)
  Rule written: direct mapping from Av.fesom
- [ ] **difmxybo** — Momentum XY Biharmonic Diffusivity (`m4 s-1`, yr, 3D)
  BLOCKED: FESOM doesn't output biharmonic coefficient separately
- [ ] **diftrelo** — Tracer Epineutral Laplacian Diffusivity (`m2 s-1`, yr, 3D)
  Possible: fer_K.fesom if Fer_GM=.true. (GM diffusivity); check config
- [ ] **diftrblo** — Tracer Diffusivity from Mesoscale Parameterization (`m2 s-1`, yr, 3D)
  Possible: same as diftrelo (fer_K) under Fer_GM
- [x] **rsdoabsorb** — Shortwave Absorption by Ocean Layer (`W m-2`, yr, 3D)
  FESOM2 source modified: computed from sw_3d in gen_modules_cmor_diag.F90

## Yearly energy diagnostics (Oyr)

- [ ] **dispkexyfo** — KE Dissipation from XY Friction (`W m-2`, yr)
  BLOCKED: no KE dissipation diagnostic
- [ ] **tnkebto** — KE Tendency from Eddy Advection (`W m-2`, yr)
  BLOCKED: no KE tendency diagnostic
- [ ] **tnpeo** — Tendency of Potential Energy (`W m-2`, yr)
  BLOCKED: no PE tendency diagnostic

## Water isotopes (Emon) — require lwiso=.true.

- [~] **sw17O** — Isotopic Ratio 17O (`1`, mon, 3D) — SKIPPED: lwiso not enabled
- [~] **sw18O** — Isotopic Ratio 18O (`1`, mon, 3D) — SKIPPED
- [~] **sw2H** — Isotopic Ratio Deuterium (`1`, mon, 3D) — SKIPPED

## Not applicable to FESOM2

- [~] **bigthetao** (all frequencies) — FESOM uses potential temperature, not conservative
- [~] **chcint** — Conservative temperature heat content — same reason
- [~] **ocontemp*** — All conservative temperature tendency terms — same reason
- [~] **thkcelluo** — Cell thickness at u-points — unstructured mesh, no u/v grid distinction
- [~] **thkcellvo** — Cell thickness at v-points — same
- [~] **dxto/dyto/dxuo/dyuo/dxvo/dyvo** — Cell lengths at staggered points — unstructured mesh

---

## Summary

| Category | Count | Done | Status |
|----------|-------|------|--------|
| Feasible from existing output | ~16 | 16 | DONE |
| Medium (bottom extract, integration, volcello) | ~10 | 9 | mostly done |
| Yearly diffusivity | 3 | 3 | DONE |
| Decadal | ~10 | 9 | mostly done |
| Hard (streamfunction, tendencies) | ~4 | 2 | 2 done, 1 commented (sfx/sfy), 1 blocked |
| Needs namelist.io additions | 5 | 5 | DONE (rules written, awaiting model re-run) |
| FESOM2 source changes (tendencies + SW) | 7 | 7 | DONE (code added, needs compile+test) |
| Needs basin masks (external data) | ~12 | 0 | BLOCKED |
| Requires online diagnostics (remaining) | ~8 | 0 | BLOCKED |
| Not applicable (conservative T / isotopes / unstructured) | ~26 | — | SKIPPED |

Total rules written: **46** (+ 1 commented placeholder for sfx/sfy)
FESOM2 source additions: **6** new diagnostic outputs (osalttend, opottempdiff, opottemprmadvect, osaltdiff, osaltrmadvect, rsdoabsorb)
