# CMIP7 CAP7 Sea Ice Variables — AWI-ESM3-VEG-HR

Status of CAP7 (extra priority) sea ice variables for FESOM 2.7 / AWI-ESM3.
These are lower priority than core variables but still important.

**Key model constraints:**
- FESOM's own sea ice (NOT icepack) — single-category, no ITD
- mEVP rheology (whichevp=1)
- Melt ponds enabled (use_meltponds=.true.)
- No ice age tracer (tr_iage=.false.)
- No ridged ice tracer (tr_lvl=.false.)
- vec_autorotate=.true. for velocity/stress rotation
- ldiag_cmor=.true. for hemisphere-integrated scalars

Sources: cmip7_CAP7extra_variables_seaIce.csv, cmip7_CAP7extra_variables_ocean_seaIce.csv

## SImon — Monthly variables

### Radiation fluxes over sea ice (from atmosphere coupling)
- [ ] **rlds** — Downwelling Longwave Flux over Sea Ice (`W m-2`, high) — likely from OpenIFS, not FESOM output
- [ ] **rlus** — Upwelling Longwave Flux over Sea Ice (`W m-2`, high) — likely from OpenIFS, not FESOM output
- [ ] **rsds** — Downwelling Shortwave Flux over Sea Ice (`W m-2`, high) — likely from OpenIFS; FESOM has `qsi` (ice heat flux) under __oifs
- [ ] **rsus** — Upwelling Shortwave Flux over Sea Ice (`W m-2`, high) — likely from OpenIFS

### Heat fluxes
- [x] **siflcondbot** — Net Conductive Heat Flux at Ice Base (`W m-2`, high) — qcon (DefaultPipeline)
- [x] **siflcondtop** — Net Conductive Heat Flux at Ice Surface (`W m-2`, high) — k_ice*(T_base-ist)/h_ice (siflcondtop_pipeline)
- [ ] **sifllattop** — Net Latent Heat Flux over Sea Ice (`W m-2`, high) — from atmosphere coupling
- [ ] **siflsensbot** — Net Upward Sensible Heat Flux under Sea Ice (`W m-2`, high) — ocean-ice interface
- [ ] **siflsenstop** — Net Downward Sensible Heat Flux over Sea Ice (`W m-2`, high) — atmosphere-ice interface
- [ ] **siflswdbot** — Downwelling Shortwave Flux under Sea Ice (`W m-2`, high) — transmitted through ice
- [x] **sihc** — Sea-Ice Heat Content (`J m-2`, high) — rho_ice*h_ice*(c_ice*(T_mean-T_melt)-L_f) (sihc_pipeline)

### Ice/snow heat content
- [x] **sisnhc** — Snow Heat Content (`J m-2`, high) — -rho_snow*L_f*h_snow (sisnhc_pipeline)

### Thermodynamic/dynamic tendencies
- [x] **sidconcdyn** — Area Fraction Tendency from Dynamics (`s-1`, high) — dyngrarea (DefaultPipeline)
- [x] **sidconcth** — Area Fraction Tendency from Thermodynamics (`s-1`, high) — thdgrarea (DefaultPipeline)
- [x] **sidmassdyn** — Mass Change from Dynamics (`kg m-2 s-1`, high) — dyngrice × rho_ice=910 (scale_pipeline)
- [x] **sidmassth** — Mass Change from Thermodynamics (`kg m-2 s-1`, high) — thdgrice × rho_ice=910 (scale_pipeline)
- [ ] **sidmassgrowthbot** — Mass Change Through Basal Growth (`kg m-2 s-1`, high) — NOT AVAILABLE: no split growth terms
- [ ] **sidmassgrowthsi** — Mass Change Through Snow-to-Ice Conversion (`kg m-2 s-1`, high) — NOT AVAILABLE
- [ ] **sidmassgrowthwat** — Mass Change Through Frazil Growth (`kg m-2 s-1`, high) — NOT AVAILABLE
- [ ] **sidmassmeltbot** — Mass Change Through Bottom Melting (`kg m-2 s-1`, high) — NOT AVAILABLE: no split melt terms
- [ ] **sidmassmeltlat** — Mass Change Through Lateral Melting (`kg m-2 s-1`, high) — NOT AVAILABLE
- [ ] **sidmassmelttop** — Mass Change Through Surface Melting (`kg m-2 s-1`, high) — NOT AVAILABLE

### Freshwater and salt fluxes
- [ ] **sbl** — Snow Sublimation Rate (`kg m-2 s-1`, high) — not directly output; part of atmosphere coupling
- [x] **snm** — Snow Melt Rate (`kg m-2 s-1`, high) — thdgrsn × rho_snow=330 (scale_pipeline)
- [x] **sfdsi** — Salt Flux from Sea Ice (`kg m-2 s-1`, medium) — realsalt (scale_pipeline, factor needs verification)
- [x] **siflfwbot** — Freshwater Flux from Sea Ice (`kg m-2 s-1`, medium) — fw_ice × rho_water=1000 (scale_pipeline)
- [x] **siflfwdrain** — Freshwater Flux from Sea-Ice Surface (`kg m-2 s-1`, medium) — fw_snw × rho_water=1000 (scale_pipeline)
- [x] **sisaltmass** — Mass of Salt in Sea Ice (`kg m-2`, high) — m_ice × 0.004 (sice=4 psu, scale_pipeline)

### Stress and force balance
- [x] **sistrxdtop** — X-Component Atmospheric Stress on Ice (`N m-2`, high) — atmice_x (DefaultPipeline)
- [x] **sistrydtop** — Y-Component Atmospheric Stress on Ice (`N m-2`, high) — atmice_y (DefaultPipeline)
- [x] **sistrxubot** — X-Component Ocean Stress on Ice (`N m-2`, high) — iceoce_x (DefaultPipeline)
- [x] **sistryubot** — Y-Component Ocean Stress on Ice (`N m-2`, high) — iceoce_y (DefaultPipeline)
- [ ] **siforcecoriolx** — Coriolis Force X (`N m-2`, medium) — NOT AVAILABLE: not output by FESOM
- [ ] **siforcecorioly** — Coriolis Force Y (`N m-2`, medium) — NOT AVAILABLE
- [ ] **siforceintstrx** — Internal Stress X (`N m-2`, medium) — NOT AVAILABLE
- [ ] **siforceintstry** — Internal Stress Y (`N m-2`, medium) — NOT AVAILABLE
- [ ] **siforcetiltx** — Sea-Surface Tilt X (`N m-2`, medium) — NOT AVAILABLE
- [ ] **siforcetilty** — Sea-Surface Tilt Y (`N m-2`, medium) — NOT AVAILABLE

### Ice dynamics derived
- [x] **sispeed** — Sea-Ice Speed (`m s-1`, high) — sqrt(uice² + vice²) (sispeed_pipeline)
- [ ] **sidivvel** — Divergence of Ice Velocity Field (`s-1`, medium) — NOT AVAILABLE: needs spatial derivatives on unstructured grid
- [ ] **sishearvel** — Maximum Shear of Ice Velocity Field (`s-1`, medium) — NOT AVAILABLE: needs spatial derivatives
- [x] **sidmasstranx** — X-Component Ice Mass Transport (`kg s-1`, medium) — uice × m_ice (ice_mass_transport_pipeline)
- [x] **sidmasstrany** — Y-Component Ice Mass Transport (`kg s-1`, medium) — vice × m_ice (ice_mass_transport_pipeline)

### Mechanical properties
- [x] **sicompstren** — Compressive Sea Ice Strength (`N m-1`, medium) — strength_ice (DefaultPipeline)
- [x] **sistressave** — Average Normal Stress (`N m-1`, high) — (sgm11+sgm22)/2 (sistressave_pipeline)
- [x] **sistressmax** — Maximum Shear Stress (`N m-1`, high) — from sgm11/12/22 (sistressmax_pipeline)

### Other
- [x] **sitempbot** — Temperature at Ice-Ocean Interface (`K`, medium) — T_freeze from SSS (sitempbot_pipeline)
- [x] **sifb** — Sea-Ice Freeboard (`m`, medium) — from h_ice, h_snow, densities (sifb_pipeline)
- [x] **sidragbot** — Ocean Drag Coefficient (`1`, medium) — constant 0.0055 (constant_field_pipeline)
- [ ] **sidragtop** — Atmospheric Drag Coefficient (`1`, medium) — from atmosphere coupling, may be constant

### Hemisphere-integrated scalars (ldiag_cmor=.true.)
- [x] **siarea (N)** — Sea-Ice Area North (`1e6 km2`, high) — siarean (DefaultPipeline)
- [x] **siarea (S)** — Sea-Ice Area South (`1e6 km2`, high) — siareas (DefaultPipeline)
- [x] **siextent (N)** — Sea-Ice Extent North (`1e6 km2`, high) — siextentn (DefaultPipeline)
- [x] **siextent (S)** — Sea-Ice Extent South (`1e6 km2`, high) — siextents (DefaultPipeline)
- [x] **sivol (N)** — Sea-Ice Volume North (`1e3 km3`, high) — sivoln (DefaultPipeline)
- [x] **sivol (S)** — Sea-Ice Volume South (`1e3 km3`, high) — sivols (DefaultPipeline)
- [x] **sisnmass (N)** — Snow Mass on Sea Ice North (`kg`, high) — m_snow × cell_area, lat≥0 (sisnmass_pipeline)
- [x] **sisnmass (S)** — Snow Mass on Sea Ice South (`kg`, high) — m_snow × cell_area, lat<0 (sisnmass_pipeline)

### Melt ponds (use_meltponds=.true.)
- [x] **simpconc** — Melt Pond Fraction (`%`, high) — apnd × 100 (fraction_to_percent_pipeline)
- [x] **simpeffconc** — Effective Melt Pond Fraction (`%`, medium) — apnd*(1-ipnd/hpnd)*100 (simpeffconc_pipeline)
- [x] **simpthick** — Melt Pond Depth (`m`, medium) — hpnd (DefaultPipeline)
- [x] **simprefrozen** — Refrozen Ice on Melt Pond (`m`, medium) — ipnd (DefaultPipeline)

### Strait fluxes
- [ ] **siareaacrossline** — Ice Area Flux Through Straits (`m2 s-1`, high) — NOT AVAILABLE: no strait diagnostics
- [ ] **simassacrossline** — Ice Mass Flux Through Straits (`kg s-1`, high) — NOT AVAILABLE
- [ ] **sisnmassacrossline** — Snow Mass Flux Through Straits (`kg s-1`, high) — NOT AVAILABLE

## NOT AVAILABLE — requires physics not in this configuration

- [ ] **siage** (day/mon) — Ice Age — tr_iage=.false., not enabled
- [ ] **sirdgconc** — Ridged Ice Fraction — tr_lvl=.false., no ridging tracer
- [ ] **sithick (ridged)** — Ridged Ice Thickness — tr_lvl=.false.
- [ ] **siitdconc** — Ice Area by Thickness Category — no ITD (single-category FESOM ice, not icepack)
- [ ] **siitdthick** — Ice Thickness by Category — no ITD
- [ ] **siitdsnconc** — Snow Area by Thickness Category — no ITD
- [ ] **siitdsnthick** — Snow Thickness by Category — no ITD
- [ ] **sisndmassdyn** — Snow Mass Change from Dynamics — not output separately
- [ ] **sisndmasssi** — Snow Mass Change from Snow-to-Ice Conversion — not output separately
- [ ] **sisndmasswind** — Snow Mass Change from Wind Drift — not output (no wind redistribution)

## SIday — Daily variables
- [ ] **rsds** — Downwelling Shortwave (`W m-2`, high) — from atmosphere
- [ ] **rsus** — Upwelling Shortwave (`W m-2`, high) — from atmosphere
- [ ] **siage** — Ice Age (`s`, high) — NOT AVAILABLE: tr_iage=.false.
- [ ] **siconca** — Ice Area on Atm Grid (`%`, high) — needs regridding a_ice to atmosphere grid
- [x] **sispeed** — Ice Speed (`m s-1`, high) — sqrt(uice²+vice²) (sispeed_pipeline, daily uice/vice added to namelist)
- [x] **sitimefrac** — Fraction of Time with Ice (`1`, high) — daily a_ice>0 (more accurate than monthly)
- [x] **ts** — Surface Temperature (`K`, high) — daily ist (added to namelist)
- [ ] **siarea (N/S)** — daily hemisphere areas — ldiag_cmor scalars (need to verify daily output)
- [ ] **siextent (N/S)** — daily hemisphere extents — ldiag_cmor scalars (need to verify daily output)
- [ ] **sivol (N/S)** — daily hemisphere volumes — ldiag_cmor scalars (need to verify daily output)
- [x] **sisnmass (N/S)** — daily hemisphere snow mass — hemisphere_integral_pipeline (daily m_snow added to namelist)

## SImon — cross-realm (ocean seaIce)
- [x] **sfdsi** — Downward Sea Ice Basal Salt Flux (`kg m-2 s-1`, medium) — realsalt (scale_pipeline, factor needs verification)
- [x] **siflfwbot** — Water Flux into Ocean from Ice Thermodynamics (`kg m-2 s-1`, medium) — fw_ice × 1000 (scale_pipeline)
- [x] **vsfsit** — Virtual Salt Flux from Ice Thermodynamics (`kg m-2 s-1`, medium) — virtsalt (scale_pipeline, factor needs verification)

## Blockers

1. **Radiation fluxes** (rlds, rlus, rsds, rsus): These come from the atmosphere model (OpenIFS), not FESOM. Need separate atmosphere CMORization or coupling interface output.
2. **Split thermodynamic budget** (sidmassgrowthbot/si/wat, sidmassmeltbot/lat/top): FESOM outputs total thermo/dynamic tendency but not individual budget terms.
3. **Force balance terms** (siforcecoriol/intstr/tilt x/y): Not output by FESOM.
4. **ITD variables** (siitdconc/thick/snconc/snthick): No ice thickness distribution — FESOM uses single-category ice (icepack not active).
5. **Ice age** (siage): Tracer not enabled (tr_iage=.false.).
6. **Ridged ice** (sirdgconc, ridged sithick): Tracer not enabled (tr_lvl=.false.).
7. **Strait fluxes** (siareaacrossline, simassacrossline, sisnmassacrossline): No strait diagnostic in FESOM.
8. **Snow budget split** (sisndmassdyn/si/wind): Not output separately.
9. ~~**Melt ponds**~~: RESOLVED — FESOM outputs apnd, hpnd, ipnd when use_meltponds=.true. Added to namelist.io.
10. **Spatial derivatives** (sidivvel, sishearvel): Require computing divergence/shear on unstructured mesh — non-trivial post-processing.
