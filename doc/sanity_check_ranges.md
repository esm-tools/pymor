# CMIP7 AWI-ESM3-VEG-HR — Output Sanity-Check Reference Table

Expected value ranges for every variable produced across the 17 rule yamls in
`awi-esm3-veg-hr-variables/`, for pre-industrial control (piControl, ~1850)
conditions.

**Values are reference estimates from published CMIP6/CMIP5 literature,
standard climatologies (ERA5, WOA, GPCP, CERES-EBAF, HadCRUT, HadISST, LUH2,
NSIDC, PIOMAS, MODIS, Friedlingstein Global Carbon Budget, IPCC AR6), and
physical reasoning.** They were derived without reading any of this system's
output files, so they can be used as an independent sanity check.

- **Expected Min / Max**: plausible minimum/maximum grid-cell value globally.
- **Expected Mean**: area-weighted global annual mean.
- **Units**: exactly as produced by the pipeline (no conversions applied).
- piControl-specific zeros applied to all anthropogenic LUC/harvest/product
  variables and to drift-sensitive quantities.

| Variable | Realm | Units | Expected Min | Expected Mean | Expected Max | Source/Rationale |
|---|---|---|---|---|---|---|
| absscint | ocean | kg m-2 | 0 | ~140 | ~400 | Depth-integrated salinity: ~35 g/kg * 1035 kg/m3 * depth; WOA climatology |
| areacella | atmos | m2 | ~1e8 | ~5e10 | ~6e10 | Typical 1deg grid cell area; Earth surface 5.1e14 m2 / Ngrid |
| areacello | ocean | m2 | ~1e7 | ~4e10 | ~6e10 | Ocean grid cell; FESOM unstructured varies with resolution |
| areacellr | land | m2 | ~1e7 | ~5e10 | ~6e10 | River grid cell, order 1deg |
| baresoilFrac | land | % | 0 | ~10 | 100 | Sahara/Antarctica ~100%; global land ~10-15% bare (CMIP6 LUH2) |
| basin | ocean | 1 | 0 | - | ~10 | Integer region index; basin masks IPCC AR6 |
| bldep | atmos | m | ~50 | ~600 | ~3000 | PBL height; ERA5 climatology, deepest over subtropical deserts |
| burntFractionAll | land | % | 0 | ~1 | ~30 | GFED4 climatology, savanna fire belt |
| c3PftFrac | land | % | 0 | ~25 | 100 | LUH2/CMIP6 PFT distribution |
| c4PftFrac | land | % | 0 | ~5 | 100 | LUH2 C4 grasses tropical |
| ci | atmos | 1 | 0 | ~0.1 | 1 | Convection fraction; ITCZ higher |
| cLand | land | kg m-2 | 0 | ~25 | ~80 | Total land C ~2000 PgC / land area; IPCC AR6 carbon cycle |
| cl | atmos | % | 0 | ~30 | 100 | CMIP6 cloud cover profile |
| cLeaf | land | kg m-2 | 0 | ~0.3 | ~2 | Leaf C; tropical forest LAI; TRENDY |
| cli | atmos | kg kg-1 | 0 | ~1e-6 | ~1e-3 | Cloud ice mixing ratio; ERA5/CMIP |
| cLitterCwd | land | kg m-2 | 0 | ~1 | ~10 | CWD stocks; Pan et al. 2011 |
| cLitter | land | kg m-2 | 0 | ~2 | ~15 | Litter pool; IPCC AR6 |
| cLitterLut | land | kg m-2 | 0 | ~2 | ~15 | Per-tile litter; LUH2 |
| cLitterSubSurf | land | kg m-2 | 0 | ~1 | ~8 | Belowground litter subset |
| cLitterSurf | land | kg m-2 | 0 | ~1 | ~8 | Aboveground litter subset |
| clivi | atmos | kg m-2 | 0 | ~0.02 | ~1 | Ice water path; CloudSat/CERES |
| clt | atmos | % | 0 | ~66 | 100 | ISCCP global mean cloud cover ~66% |
| clw | atmos | kg kg-1 | 0 | ~1e-5 | ~2e-3 | Cloud liquid mixing ratio; ERA5 |
| clwvi | atmos | kg m-2 | 0 | ~0.1 | ~2 | Condensed water path; CERES/CloudSat |
| cOther | land | kg m-2 | 0 | ~0.2 | ~3 | Reproductive/other tissues small fraction |
| cProduct | land | kg m-2 | 0 | ~0 | ~0 | piControl has no land-use products; ~0 |
| cProductLut | land | kg m-2 | 0 | ~0 | ~0 | piControl LUC products ~0 |
| cRoot | land | kg m-2 | 0 | ~1 | ~10 | Root C; Jackson 1997 |
| cropFracC3 | land | % | 0 | ~0 | ~0 | piControl 1850: minimal crops; LUH2 |
| cropFracC4 | land | % | 0 | ~0 | ~0 | piControl 1850 |
| cropFrac | land | % | 0 | ~5 | ~100 | 1850 cropland ~5% global land; LUH2 |
| cSoil | land | kg m-2 | 0 | ~15 | ~100 | Soil C HWSD; peatlands high |
| cSoilLut | land | kg m-2 | 0 | ~15 | ~100 | Per-tile soil C |
| cStem | land | kg m-2 | 0 | ~3 | ~25 | Stem C; tropical forests |
| cVeg | land | kg m-2 | 0 | ~5 | ~35 | Vegetation C; IPCC AR6 ~450 PgC |
| cVegLut | land | kg m-2 | 0 | ~5 | ~35 | Per-tile vegetation C |
| dcw | land | kg m-2 | -5 | ~0 | 5 | Change in interception; near zero annual mean |
| deptho | ocean | m | 0 | ~3700 | ~11000 | Mean ocean depth; Mariana trench max |
| dgw | land | kg m-2 | -50 | ~0 | 50 | Annual groundwater change ~0 in steady state |
| difmxylo | ocean | m2 s-1 | 0 | ~1000 | ~1e4 | Laplacian horizontal viscosity typical |
| difvho | ocean | m2 s-1 | ~1e-6 | ~1e-4 | ~1e-2 | Vertical diffusivity; Munk/Ledwell |
| difvso | ocean | m2 s-1 | ~1e-6 | ~1e-4 | ~1e-2 | Vertical salt diffusivity |
| dslw | land | kg m-2 | -100 | ~0 | 100 | Soil moisture change; steady state ~0 |
| dsn | land | kg m-2 | -500 | ~0 | 500 | SWE change annual; ~0 in steady state |
| dsw | land | kg m-2 | -50 | ~0 | 50 | Surface water storage change ~0 |
| emibbbc | aerosol | kg m-2 s-1 | 0 | ~1e-13 | ~1e-10 | 1850 BB BC emissions; CMIP6 input4MIPs |
| emibbch4 | aerosol | kg m-2 s-1 | 0 | ~1e-12 | ~1e-9 | 1850 BB CH4; CMIP6 |
| emibbco | aerosol | kg m-2 s-1 | 0 | ~1e-11 | ~1e-8 | 1850 BB CO; CMIP6 |
| emibbdms | aerosol | kg m-2 s-1 | 0 | ~0 | ~1e-12 | DMS from BB small |
| emibboa | aerosol | kg m-2 s-1 | 0 | ~1e-12 | ~1e-9 | 1850 BB OA; CMIP6 |
| emibbso2 | aerosol | kg m-2 s-1 | 0 | ~1e-13 | ~1e-10 | 1850 BB SO2; CMIP6 |
| emibbvoc | aerosol | kg m-2 s-1 | 0 | ~1e-12 | ~1e-9 | 1850 BB NMVOC; CMIP6 |
| esn | land | kg m-2 s-1 | 0 | ~1e-6 | ~5e-5 | Snow sublimation; polar climatology |
| evspsbl | atmos | kg m-2 s-1 | 0 | ~3.2e-5 | ~2e-4 | Global mean E ~2.8 mm/day; GPCP/ERA5 |
| evspsblpot | land | kg m-2 s-1 | 0 | ~5e-5 | ~3e-4 | PET highest subtropics |
| evspsblsoi | land | kg m-2 s-1 | 0 | ~1e-5 | ~1e-4 | Soil evap component |
| evspsblveg | land | kg m-2 s-1 | 0 | ~1e-5 | ~1.5e-4 | Canopy evap/transpiration |
| fAnthDisturb | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl: no anthropogenic; ~0 |
| fBNF | land | kg m-2 s-1 | 0 | ~3e-12 | ~3e-11 | Biological N fixation ~100 TgN/yr; Vitousek |
| fCLandToOcean | land | kg m-2 s-1 | 0 | ~1e-11 | ~1e-9 | Riverine C ~0.9 PgC/yr; IPCC AR6 |
| fDeforestToAtmos | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl: no deforestation |
| fDeforestToProduct | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl: no deforestation |
| fFireAll | land | kg m-2 s-1 | 0 | ~5e-11 | ~5e-9 | GFED ~2 PgC/yr global |
| fFire | land | kg m-2 s-1 | 0 | ~5e-11 | ~5e-9 | Natural fire dominant in piControl |
| fFireNat | land | kg m-2 s-1 | 0 | ~5e-11 | ~5e-9 | GFED natural |
| fHarvestToAtmos | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl: negligible harvest |
| fLitterFire | land | kg m-2 s-1 | 0 | ~2e-11 | ~2e-9 | Litter burning component |
| fLitterSoil | land | kg m-2 s-1 | 0 | ~2e-9 | ~5e-8 | Litter->soil turnover |
| fLuc | land | kg m-2 s-1 | -1e-9 | ~0 | ~1e-9 | piControl LUC ~0; CMIP6 spec |
| fLulccAtmLut | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl LUC ~0 |
| fNgasFire | land | kg m-2 s-1 | 0 | ~1e-12 | ~1e-10 | N from fires small fraction |
| fNgas | land | kg m-2 s-1 | 0 | ~3e-12 | ~3e-10 | Gaseous N loss |
| fNLandToOcean | land | kg m-2 s-1 | 0 | ~1e-12 | ~1e-10 | Riverine N flux ~40 TgN/yr |
| fNleach | land | kg m-2 s-1 | 0 | ~1e-12 | ~1e-10 | N leaching |
| fNLitterSoil | land | kg m-2 s-1 | 0 | ~3e-11 | ~1e-9 | N litter-to-soil |
| fNloss | land | kg m-2 s-1 | 0 | ~5e-12 | ~5e-10 | Total N loss |
| fNup | land | kg m-2 s-1 | 0 | ~3e-10 | ~3e-8 | Plant N uptake; Cleveland |
| fProductDecomp | land | kg m-2 s-1 | 0 | ~0 | ~0 | piControl products ~0 |
| fracInLut | land | % | 0 | ~0 | ~0 | piControl no LU transitions |
| fracLut | land | % | 0 | ~25 | 100 | Per-tile fraction; LUH2 |
| fracOutLut | land | % | 0 | ~0 | ~0 | piControl no LU transitions |
| friver | ocean | kg m-2 s-1 | 0 | ~1e-5 | ~1e-2 | River discharge, Amazon mouth high |
| fVegFire | land | kg m-2 s-1 | 0 | ~3e-11 | ~3e-9 | Vegetation fire C flux |
| fVegLitter | land | kg m-2 s-1 | 0 | ~2e-9 | ~5e-8 | Litterfall ~60 PgC/yr |
| gpp | land | kg m-2 s-1 | 0 | ~3.5e-8 | ~1e-7 | GPP ~120 PgC/yr; Beer 2010 |
| gppLut | land | kg m-2 s-1 | 0 | ~3.5e-8 | ~1e-7 | Per-tile GPP |
| grassFrac | land | % | 0 | ~20 | 100 | Natural grass coverage; LUH2 |
| hfdsl | land | W m-2 | -100 | ~0 | 100 | Ground heat flux annual ~0 |
| hfds | ocean | W m-2 | -300 | ~2 | 300 | Net heat into ocean; ~2 W/m2 piControl drift |
| hfls | atmos | W m-2 | 0 | ~80 | 250 | LH flux; CERES/ERA5 |
| hfss | atmos | W m-2 | -50 | ~20 | 150 | SH flux; CERES/ERA5 |
| hfx | ocean | W | -2e15 | ~0 | 2e15 | Zonal heat transport; Trenberth |
| hfy | ocean | W | -2e15 | ~0 | 2e15 | Meridional heat transport peak ~2 PW |
| hur | atmos | % | 0 | ~60 | 100 | RH profile; ERA5 |
| hurs | atmos | % | 10 | ~75 | 100 | Near-surface RH; ERA5 |
| hus | atmos | 1 | ~1e-6 | ~3e-3 | ~0.025 | Specific humidity; tropics saturated ~25 g/kg |
| huss | atmos | 1 | ~0.00001 | ~0.008 | ~0.025 | ERA5 near-surface q, polar dry to tropical moist |
| irrLut | land | kg m-2 s-1 | 0 | ~0 (piControl) | ~1e-5 | No anthropogenic irrigation in 1850 piControl |
| lai | land | 1 | 0 | ~1.2 | ~7 | MODIS LAI climatology, tropical forests peak |
| laiLut | land | 1 | 0 | ~1.2 | ~7 | MODIS per-tile LAI |
| landCoverFrac | land | % | 0 | varies by PFT | 100 | Fraction bounded 0-100 |
| lwp | aerosol | kg m-2 | 0 | ~0.05-0.1 | ~0.5 | CMIP6/ISCCP cloud LWP climatology |
| masscello | ocean | kg m-2 | ~0 | ~1e5-1e6 | ~1e7 | rho*dz per layer, ~1025*dz |
| masso | ocean | kg | 1.3e21 | 1.35e21 | 1.4e21 | Global ocean mass ~1.35e21 kg |
| mlotst | ocean | m | ~10 | ~60 | ~2000 | de Boyer Montegut climatology; deep Labrador/Weddell |
| mlotstsq | ocean | m2 | 100 | ~1e4 | ~4e6 | Square of mlotst |
| mrfso | landIce | kg m-2 | 0 | ~200 | ~5000 | Frozen soil water, permafrost regions |
| mrrob | land | kg m-2 s-1 | 0 | ~1e-5 | ~1e-4 | Subsurface runoff, wettest tropics |
| mrro | land | kg m-2 s-1 | 0 | ~1e-5 (30 mm/yr land avg) | ~2e-4 | GRDC/CMIP6 land runoff |
| mrros | land | kg m-2 s-1 | 0 | ~5e-6 | ~1e-4 | Surface runoff fraction of total |
| mrsofc | land | kg m-2 | 0 | ~300 | ~1500 | Soil field capacity, typical 300mm |
| mrso | land | kg m-2 | 0 | ~500 | ~2000 | Total soil moisture column |
| mrsol | land | kg m-2 | 0 | ~100 | ~500 | Upper soil layer water |
| mrsolLut | land | kg m-2 | 0 | ~100 | ~500 | Per-tile upper soil moisture |
| mrsow | land | 1 | 0 | ~0.5 | 1 | Soil wetness fraction |
| mrtws | land | kg m-2 | 0 | ~1500 | ~1e5 | GRACE TWS incl. groundwater/ice |
| msftbarot | ocean | kg s-1 | -2e11 | 0 | 2e11 | ACC ~150 Sv *1025 kg/m3 |
| msftmmpa | ocean | kg s-1 | -5e10 | 0 | 5e10 | Mesoscale MOC component smaller than resolved |
| msftm | ocean | kg s-1 | -2e10 | 0 | 2e10 | AMOC ~15-20 Sv; CMIP6 piControl |
| nbp | land | kg m-2 s-1 | -1e-7 | ~0 (piControl balanced) | 1e-7 | piControl NBP near zero, Friedlingstein 2022 |
| nep | land | kg m-2 s-1 | -5e-8 | ~0 | 5e-8 | NEP near zero annual mean in piControl |
| nLand | land | kg m-2 | 0 | ~1.5 | ~20 | Total N in soil+veg, ~200 PgN / land |
| nLitter | land | kg m-2 | 0 | ~0.05 | ~1 | Litter N, small pool |
| nMineral | land | kg m-2 | 0 | ~0.05 | ~1 | Mineral/inorganic soil N |
| npp | land | kg m-2 s-1 | 0 | ~1.9e-8 (~60 PgC/yr/land) | ~5e-7 | CMIP6 NPP, tropical forests |
| nppLut | land | kg m-2 s-1 | 0 | ~1.9e-8 | ~5e-7 | Per-tile NPP |
| nProduct | land | kg m-2 | 0 | ~0 (piControl) | ~0.01 | No land-use products in piControl |
| nSoil | land | kg m-2 | 0 | ~1 | ~15 | Soil N dominates total |
| nVeg | land | kg m-2 | 0 | ~0.1 | ~2 | Vegetation N pool |
| obvfsq | ocean | s-2 | 0 | ~1e-5 | ~1e-3 | N^2 pycnocline values |
| od550aer | aerosol | 1 | ~0.02 | ~0.12 | ~1 | MODIS/AERONET AOD climatology |
| opottempdiff | ocean | W m-2 | -50 | ~0 | 50 | Diapycnal mixing tendency small |
| opottempmint | ocean | degC kg m-2 | -1e7 | ~1e7 | 1e8 | rho*theta*depth, ~1025*10*4000 tropics |
| opottemprmadvect | ocean | W m-2 | -500 | ~0 | 500 | Advective heat tendency |
| opottemptend | ocean | W m-2 | -500 | ~0 | 500 | Total theta tendency, piControl near 0 global |
| orog | land | m | 0 | ~800 | ~8848 | ETOPO topography |
| osaltdiff | ocean | kg m-2 s-1 | -1e-5 | ~0 | 1e-5 | Salt tendency from mixing |
| osaltrmadvect | ocean | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | Advective salt tendency |
| osalttend | ocean | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | Total salt tendency ~0 in piControl |
| pastureFracC3 | land | % | 0 | ~0 (piControl) | ~5 | Minimal pasture in 1850 |
| pastureFracC4 | land | % | 0 | ~0 (piControl) | ~5 | Minimal pasture in 1850 |
| pastureFrac | land | % | 0 | ~3 | ~50 | LUH2 1850 pasture mostly low |
| pbo | ocean | Pa | 0 | ~4e7 | ~1.1e8 | rho*g*H; 4000m ocean |
| pfull | atmos | Pa | ~1 | ~5e4 | ~101325 | Model level pressures |
| phcint | ocean | J m-2 | 0 | ~1e10 | ~5e10 | Ocean heat content rho*cp*T*H |
| pr | atmos | kg m-2 s-1 | 0 | ~3e-5 (~2.7 mm/day) | ~3e-4 | GPCP global mean precip |
| prc | atmos | kg m-2 s-1 | 0 | ~1.5e-5 | ~2e-4 | Convective fraction ~50% |
| prra | seaIce | kg m-2 s-1 | 0 | ~1e-6 | ~1e-4 | Rain over sea ice rare |
| prsn | atmos | kg m-2 s-1 | 0 | ~5e-6 | ~1e-4 | Snowfall ~15% of precip |
| prveg | land | kg m-2 s-1 | 0 | ~1e-5 | ~3e-4 | Canopy-intercepted precip |
| prw | atmos | kg m-2 | 0.5 | ~25 | ~70 | ERA5 TCWV climatology |
| ps | atmos | Pa | 50000 | ~98500 | 105000 | Surface pressure range incl. Tibet |
| psl | atmos | Pa | 95000 | ~101325 | 105000 | MSLP ERA5 |
| pso | ocean | Pa | ~0 | ~101325 | ~102000 | Sea surface pressure ~atmospheric |
| ra | land | kg m-2 s-1 | 0 | ~2e-8 | ~5e-7 | Autotrophic resp ~60 PgC/yr |
| raLeaf | land | kg m-2 s-1 | 0 | ~5e-9 | ~1e-7 | Leaf resp fraction of ra |
| raLut | land | kg m-2 s-1 | 0 | ~2e-8 | ~5e-7 | Per-tile ra |
| raOther | land | kg m-2 s-1 | 0 | ~5e-9 | ~1e-7 | Small ra fraction |
| raRoot | land | kg m-2 s-1 | 0 | ~5e-9 | ~1e-7 | Root resp fraction |
| raStem | land | kg m-2 s-1 | 0 | ~5e-9 | ~1e-7 | Stem resp fraction |
| residualFrac | land | % | 0 | ~5 | 100 | Bare/urban/other residual |
| rh | land | kg m-2 s-1 | 0 | ~1.8e-8 (~55 PgC/yr) | ~3e-7 | Heterotrophic resp, CMIP6 |
| rhLitter | land | kg m-2 s-1 | 0 | ~9e-9 | ~1.5e-7 | Litter decomp fraction |
| rhLut | land | kg m-2 s-1 | 0 | ~1.8e-8 | ~3e-7 | Per-tile rh |
| rhSoil | land | kg m-2 s-1 | 0 | ~9e-9 | ~1.5e-7 | Soil rh component |
| rlds | atmos | W m-2 | 100 | ~345 | 450 | CERES-EBAF surface LW down |
| rldscs | atmos | W m-2 | 80 | ~315 | 430 | Clear-sky LW down |
| rls | atmos | W m-2 | -200 | ~-55 | 50 | Net LW surface (down-up) |
| rlus | atmos | W m-2 | 150 | ~398 | 520 | sigma*T^4, CERES |
| rluscs | atmos | W m-2 | 150 | ~398 | 520 | Same as rlus (clear-sky same surface T) |
| rlut | atmos | W m-2 | 120 | ~239 | 320 | CERES OLR |
| rlutcs | atmos | W m-2 | 150 | ~266 | 330 | Clear-sky OLR |
| rootd | land | m | 0 | ~2 | ~10 | Schenk & Jackson root depths |
| rsdoabsorb | ocean | W m-2 | 0 | varies by layer | ~300 | SW penetration, surface layer |
| rsds | atmos | W m-2 | 0 | ~185 | 400 | CERES surface SW down annual |
| rsdscs | atmos | W m-2 | 0 | ~245 | 450 | Clear-sky surface SW down |
| rsdt | atmos | W m-2 | 0 | ~340 | ~550 | TOA incident SW, S0/4 |
| rss | atmos | W m-2 | 0 | ~160 | 350 | Net SW surface |
| rsus | atmos | W m-2 | 0 | ~24 | 300 | Surface upward SW (albedo*rsds) |
| rsuscs | atmos | W m-2 | 0 | ~30 | 350 | Clear-sky upwelling SW surface |
| rsut | atmos | W m-2 | 0 | ~100 | 400 | CERES TOA reflected SW |
| rsutcs | atmos | W m-2 | 0 | ~53 | 300 | Clear-sky TOA reflected |
| rtmt | atmos | W m-2 | -200 | ~0 (piControl balanced) | 200 | Net TOA ~0 in piControl |
| sbl | landIce | kg m-2 s-1 | -1e-5 | ~1e-7 | 1e-5 | Snow/ice sublimation small |
| scint | ocean | kg m-2 | 0 | ~1.4e5 | ~1.5e5 | S*rho*H, ~35 PSU*1025*4000m |
| sfcWind | atmos | m s-1 | 0 | ~6.5 | ~40 | ERA5 10m wind daily max |
| sfdsi | ocean | kg m-2 s-1 | -1e-5 | ~0 | 1e-5 | Sea-ice salt flux |
| sftgif | land | % | 0 | ~3 | 100 | Glacier/ice fraction (Greenland/Antarctica=100) |
| sftlf | atmos | % | 0 | ~29 | 100 | Land fraction, ~29% globe |
| sftof | ocean | % | 0 | ~71 | 100 | Ocean fraction complement |
| sfx | ocean | kg s-1 | -1e8 | ~0 | 1e8 | 3D salt transport |
| sfy | ocean | kg s-1 | -1e8 | ~0 | 1e8 | 3D salt transport |
| shrubFrac | land | % | 0 | 5-10 | 100 | LUH2/CMIP6 land cover |
| siarea | seaIce | 1e6 km2 | 4 (Sep) | 11 | 16 (Mar) | NSIDC NH climatology |
| sicompstren | seaIce | N m-1 | 0 | 5e3 | 5e4 | Hibler rheology P* typical |
| siconc | seaIce | % | 0 | ~5 global / ~60 in ice zone | 100 | NSIDC/OSI-SAF |
| sidconcdyn | seaIce | s-1 | -1e-5 | ~0 | 1e-5 | CMIP6 sea-ice tendencies |
| sidconcth | seaIce | s-1 | -1e-5 | ~0 | 1e-5 | CMIP6 sea-ice tendencies |
| sidmassdyn | seaIce | kg m-2 s-1 | -1e-3 | ~0 | 1e-3 | CMIP6 order-of-magnitude |
| sidmassth | seaIce | kg m-2 s-1 | -1e-3 | ~0 | 1e-3 | CMIP6 order-of-magnitude |
| sidmasstranx | seaIce | kg s-1 | -1e8 | ~0 | 1e8 | Fram Strait export ~1e8 kg/s |
| sidmasstrany | seaIce | kg s-1 | -1e8 | ~0 | 1e8 | Fram Strait export ~1e8 kg/s |
| sidragbot | seaIce | 1 | 1e-3 | 5e-3 | 2e-2 | McPhee ice-ocean drag |
| sieqthick | seaIce | m | 0 | 0.3 (ice zone ~1.5) | 8 | PIOMAS climatology |
| siextent | seaIce | 1e6 km2 | 6 (Sep) | 12 | 16 (Mar) | NSIDC NH |
| sifb | seaIce | m | 0 | 0.2 | 1.5 | ICESat freeboard |
| siflcondbot | seaIce | W m-2 | -50 | ~5 | 100 | Maykut conductive flux |
| siflcondtop | seaIce | W m-2 | -50 | ~5 | 100 | Maykut conductive flux |
| siflfwbot | seaIce | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | CMIP6 ice FW flux |
| siflfwdrain | seaIce | kg m-2 s-1 | 0 | ~1e-6 | 1e-4 | Melt pond drainage |
| sihc | seaIce | J m-2 | -1e9 | -1e8 | 0 | c*rho*h*dT; negative=cold |
| simass | seaIce | kg m-2 | 0 | 30 | 5000 | h*rho_ice, up to ~5m thick |
| simpconc | seaIce | % | 0 | 5 | 50 | CICE melt-pond frac |
| simpeffconc | seaIce | % | 0 | 3 | 40 | CICE effective pond frac |
| simprefrozen | seaIce | m | 0 | 0.02 | 0.3 | CICE topo melt-pond |
| simpthick | seaIce | m | 0 | 0.05 | 0.5 | CICE melt-pond depth |
| sisaltmass | seaIce | kg m-2 | 0 | 0.15 | 25 | ~5 psu * simass/1000 |
| sisnhc | seaIce | J m-2 | -2e7 | -2e6 | 0 | c_snow*rho*h*dT |
| sisnmass | seaIce | kg | 0 | 2e15 | 1e16 | NH snow-on-ice total |
| sispeed | seaIce | m s-1 | 0 | 0.05 | 1.0 | IABP drift buoys |
| sistressave | seaIce | N m-1 | -5e4 | 0 | 5e4 | CICE stress tensor |
| sistressmax | seaIce | N m-1 | 0 | 1e3 | 5e4 | CICE stress tensor |
| sistrxdtop | seaIce | N m-2 | -1 | 0 | 1 | Atm stress on ice |
| sistrxubot | seaIce | N m-2 | -1 | 0 | 1 | Ocean stress on ice |
| sistrydtop | seaIce | N m-2 | -1 | 0 | 1 | Atm stress on ice |
| sistryubot | seaIce | N m-2 | -1 | 0 | 1 | Ocean stress on ice |
| sitempbot | seaIce | K | 271 | 271.35 | 273.15 | Freezing point sea water |
| sithick | seaIce | m | 0 | 0.3 (ice zone 1-3) | 8 | PIOMAS/ICESat |
| sitimefrac | seaIce | 1 | 0 | 0.1 | 1 | Fraction of year with ice |
| siu | seaIce | m s-1 | -1 | 0 | 1 | IABP drift buoys |
| sivol | seaIce | 1e3 km3 | 10 (Sep) | 20 | 30 (Apr) | PIOMAS NH volume |
| siv | seaIce | m s-1 | -1 | 0 | 1 | IABP drift buoys |
| slthick | land | m | 0.01 | 0.3 | 5 | JSBACH/CLM soil layers |
| snc | landIce | % | 0 | 15 | 100 | Rutgers NH snow cover |
| snd | landIce | m | 0 | 0.05 | 10 | GlobSnow/ERA5 snow depth |
| snm | landIce | kg m-2 s-1 | 0 | 1e-6 | 1e-3 | Seasonal melt rate |
| snmsl | atmos | kg m-2 s-1 | 0 | 1e-6 | 1e-3 | Snowpack runoff |
| snw | landIce | kg m-2 | 0 | 20 | 3000 | ERA5 SWE, glaciers large |
| sob | ocean | 1E-03 | 30 | 34.7 | 38 | WOA bottom salinity |
| somint | ocean | g m-2 | 1e5 | 1.4e8 | 2e8 | rho*S*H for H~4000m |
| so | ocean | 1E-03 | 30 | 34.7 | 40 | WOA salinity |
| sos | ocean | 1E-03 | 20 | 34.7 | 40 | WOA surface salinity |
| sossq | ocean | 1E-06 | 400 | 1205 | 1600 | sos squared |
| srfrad | land | W m-2 | -100 | 60 | 250 | CERES land net radiation |
| ta | atmos | K | 180 | 255 | 310 | ERA5 free-atm mean ~255K |
| tas | atmos | K | 220 | 287 | 320 | HadCRUT/ERA5 1850 ~286.7K |
| tauu | atmos | Pa | -0.5 | ~0 | 0.5 | ERA5 wind stress |
| tauuo | ocean | N m-2 | -0.5 | ~0 | 0.5 | ERA5 ocean stress |
| tauv | atmos | Pa | -0.5 | ~0 | 0.5 | ERA5 wind stress |
| tauvo | ocean | N m-2 | -0.5 | ~0 | 0.5 | ERA5 ocean stress |
| thetao | ocean | degC | -2 | 3.5 | 32 | WOA global ocean mean |
| thkcello | ocean | m | 1 | 50 | 500 | z-coord cell thickness |
| tob | ocean | degC | -2 | 1 | 10 | WOA bottom temperature |
| tos | ocean | degC | -2 | 18 | 32 | HadISST/WOA SST |
| tossq | ocean | degC2 | 0 | ~350 | 1024 | tos squared |
| toz | aerosol | m | 2.2e-3 | 3e-3 | 5e-3 | ~300 DU = 3e-3 m (TOMS) |
| tran | land | kg m-2 s-1 | 0 | 1.5e-5 | 1e-4 | GLEAM/FLUXNET transpiration |
| treeFracBdlDcd | land | % | 0 | 5 | 100 | LUH2 land cover |
| treeFrac | land | % | 0 | 30 | 100 | LUH2 preindustrial ~30% |
| ts | atmos | K | 220 | 288 | 330 | ERA5 skin temperature |
| tslsi | land | K | 220 | 285 | 330 | Land/sea-ice skin temp |
| tsn | landIce | K | 220 | 260 | 273.15 | Snow temperature ≤ 0°C |
| ua | atmos | m s-1 | -80 | ~15 (jet) / ~0 global | 100 | ERA5 zonal wind |
| uas | atmos | m s-1 | -30 | ~0 | 30 | ERA5 10m wind |
| umo | ocean | kg s-1 | -1e12 | 0 | 1e12 | Cell-scale mass transport |
| uo | ocean | m s-1 | -2 | ~0 | 2 | WOCE/Argo currents |
| uos | ocean | m s-1 | -2 | ~0 | 2.5 | OSCAR surface currents |
| va | atmos | m s-1 | -60 | ~0 | 60 | ERA5 meridional wind |
| vas | atmos | m s-1 | -30 | ~0 | 30 | ERA5 10m wind |
| vegFrac | land | % | 0 | 70 | 100 | LUH2 vegetated fraction |
| vmo | ocean | kg s-1 | -1e12 | 0 | 1e12 | Cell-scale mass transport |
| volcello | ocean | m3 | 1e6 | 1e10 | 1e12 | Grid cell volume |
| volo | ocean | m3 | 1.33e18 | 1.335e18 | 1.34e18 | Global ocean volume ~1.335e18 m3 |
| vo | ocean | m s-1 | -2 | ~0 | 2 | WOCE/Argo currents |
| vos | ocean | m s-1 | -2 | ~0 | 2.5 | OSCAR surface currents |
| vsfcorr | ocean | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | Salt flux correction |
| vsf | ocean | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | Virtual salt flux |
| vsfsit | ocean | kg m-2 s-1 | -1e-4 | ~0 | 1e-4 | Ice-related virtual salt flux |
| wap | atmos | Pa s-1 | -5 | ~0 | 5 | ERA5 omega |
| wfo | ocean | kg m-2 s-1 | -1e-4 (evap) | ~0 | 1e-4 (precip) | GPCP/CMIP6 E-P |
| wmo | ocean | kg s-1 | -1e10 | ~0 | 1e10 | Cell vertical mass transport |
| wo | ocean | m s-1 | -1e-3 | ~0 | 1e-3 | Ocean vertical velocity |
| wsg | atmos | m s-1 | 0 | 8 | 60 | ERA5 wind gust |
| zg | atmos | m | -500 | ~1e4 (mid-trop) | 35000 | Geopotential height profile |
| zos | ocean | m | -2 | 0 | 1.5 | AVISO SSH anomaly |
| zossq | ocean | m2 | 0 | 0.1 | 4 | zos squared |
| zostoga | ocean | m | -0.01 | 0 | 0.01 | piControl thermosteric ~0 |
