# Variable Coverage Report — AWI-ESM3-VEG-HR

**Total:** 742 unique (variable, frequency) pairs across all CSVs | 495 rules in YAML files

**Categories:** `core`, `cap7`, `veg`, `lrcs`, `extra`

---

## Summary

| Realm | With rules | Total | Coverage |
|---|---|---|---|
| aerosol | 0 | 31 | 0% |
| aerosol atmosChem | 0 | 14 | 0% |
| atmos | 44 | 237 | 18% |
| atmos aerosol | 0 | 1 | 0% |
| atmos aerosol land | 0 | 2 | 0% |
| atmos atmosChem aerosol | 0 | 4 | 0% |
| atmos land | 1 | 2 | 50% |
| atmosChem | 0 | 9 | 0% |
| atmosChem aerosol | 0 | 4 | 0% |
| land | 19 | 169 | 11% |
| landIce | 0 | 2 | 0% |
| landIce land | 4 | 18 | 22% |
| ocean | 58 | 153 | 37% |
| ocean seaIce | 3 | 3 | ✅ |
| seaIce | 40 | 91 | 43% |
| seaIce ocean | 1 | 2 | 50% |

---

## Realm: aerosol — 0/31 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `aerosol.abs550aer.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.bry.tavg-p39-hy-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.ccn.tavg-u-hxy-ccl.mon.glb` | ❌ | No prognostic aerosol (MACv2-SP only) | veg |
| `aerosol.cdnc.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.cfc114.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.cly.tavg-p39-hy-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.drydust.tavg-u-hxy-u.mon.glb` | ❌ | No deposition scheme | cap7 |
| `aerosol.hcl.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.hfc125.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.hfc134a.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.hno3.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.lwp.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol (MACv2-SP only) | veg |
| `aerosol.mmrpm2p5.tavg-al-hxy-u.mon.glb` | ❌ | No prognostic aerosol (MACv2-SP only) | veg |
| `aerosol.no2.tavg-h2m-hxy-u.1hr.glb` | ❌ | No atmospheric chemistry | extra |
| `aerosol.noy.tavg-p39-hy-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.o3.tavg-h2m-hxy-u.1hr.glb` | ❌ | No atmospheric chemistry | extra |
| `aerosol.o3.tmax-h2m-hxy-u.day.glb` | ❌ | No atmospheric chemistry | extra |
| `aerosol.od550aer.tavg-u-hxy-u.mon.glb` | ❌ | Realm not yet implemented | cap7 |
| `aerosol.od550bb.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550bc.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550dust.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550lt1aer.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550no3.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550oa.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550so4.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.od550soa.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol (MACv2-SP only) | veg |
| `aerosol.od550ss.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic aerosol | cap7 |
| `aerosol.oh.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.so2.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `aerosol.toz.tavg-u-hxy-u.mon.glb` | ❌ | Realm not yet implemented | cap7 |
| `aerosol.wetdust.tavg-u-hxy-u.mon.glb` | ❌ | No deposition scheme | cap7 |

---

## Realm: aerosol atmosChem — 0/14 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `aerosol.conccn.tavg-al-hxy-u.mon.glb` | ❌ | No prognostic aerosol (MACv2-SP only) | veg |
| `aerosol.emibbbc.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibbch4.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibbco.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibbdms.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibboa.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibbso2.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.emibbvoc.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `aerosol.sfpm1.tavg-h2m-hxy-u.1hr.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |
| `aerosol.sfpm1.tavg-h2m-hxy-u.day.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |
| `aerosol.sfpm10.tavg-h2m-hxy-u.1hr.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |
| `aerosol.sfpm10.tavg-h2m-hxy-u.day.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |
| `aerosol.sfpm25.tavg-h2m-hxy-u.1hr.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |
| `aerosol.sfpm25.tavg-h2m-hxy-u.day.glb` | ❌ | No prognostic aerosol (needs CAMS/M7) | extra |

---

## Realm: atmos — 44/237 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmos.albisccp.tavg-u-hxy-cl.day.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.albisccp.tavg-u-hxy-cl.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.ccb.tavg-u-hxy-ccl.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.ccb.tavg-u-hxy-ccl.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.cct.tavg-u-hxy-ccl.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.cct.tavg-u-hxy-ccl.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.ci.tavg-u-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.cl.tavg-al-hxy-u.day.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.cl.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.clc.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clcalipso.tavg-220hPa-hxy-air.day.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.clcalipso.tavg-220hPa-hxy-air.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.cldnci.tavg-u-hxy-cl.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.cldnvi.tavg-u-hxy-u.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.cli.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.clic.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clis.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clisccp.tavg-p7c-hxy-air.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.clivi.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.clivi.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.clivic.tavg-u-hxy-u.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clmisr.tavg-h16-hxy-air.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.cls.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clt.tavg-u-hxy-u.1hr.30S-90S` | ❌ | Only mon frequency implemented | extra |
| `atmos.clt.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.clt.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.cltcalipso.tavg-u-hxy-u.day.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.cltcalipso.tavg-u-hxy-u.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.cltisccp.tavg-u-hxy-u.day.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.cltisccp.tavg-u-hxy-u.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.clw.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.clwc.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clws.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.clwvi.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.clwvi.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.clwvic.tavg-u-hxy-u.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.co23D.tavg-al-hxy-u.mon.glb` | ❌ | No prognostic CO2 | cap7 |
| `atmos.co2mass.tavg-u-hm-u.mon.glb` | ❌ | No prognostic CO2 | cap7 |
| `atmos.dmc.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.edt.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.evu.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.fco2antt.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic CO2 | cap7 |
| `atmos.fco2fos.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic CO2 | cap7 |
| `atmos.fco2nat.tavg-u-hxy-u.mon.glb` | ❌ | No prognostic CO2 | cap7 |
| `atmos.hfdsnb.tavg-u-hxy-lnd.day.glb` | ❌ | Not standard IFS output | veg |
| `atmos.hfls.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.hfls.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.hfls.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.hfls.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.hfss.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.hfss.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.hfss.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.hfss.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.hur.tavg-p19-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.hur.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.hurs.tavg-h2m-hxy-u.1hr.30S-90S` | ❌ | Only mon frequency implemented | extra |
| `atmos.hurs.tpt-h2m-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.hurs.tavg-h2m-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.hurs.tavg-h2m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core, extra |
| `atmos.hurs.tavg-h2m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.hus.tpt-p6-hxy-air.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.hus.tpt-al-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.hus.tavg-p19-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.hus.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.huss.tpt-h2m-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.huss.tpt-h2m-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.huss.tavg-h2m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.huss.tavg-h2m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.loadbc.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loaddust.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadnh4.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadno3.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadoa.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadpoa.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadso4.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadsoa.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.loadss.tavg-u-hxy-u.day.glb` | ❌ | No prognostic aerosol | cap7 |
| `atmos.mc.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.mcd.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.mcu.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.noaahi2m.tavg-h2m-hxy-u.day.glb` | ❌ | Complex post-processing from T/RH | extra |
| `atmos.pctisccp.tavg-u-hxy-cl.day.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.pctisccp.tavg-u-hxy-cl.mon.glb` | ❌ | No COSP satellite simulators | cap7 |
| `atmos.pfull.tavg-al-hxy-u.day.glb` | ❌ | Needs IFS source code changes | extra |
| `atmos.pfull.tclm-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.phalf.tclm-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.pr.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, core, extra |
| `atmos.pr.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.pr.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core, extra |
| `atmos.pr.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.prc.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.prc.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.prrsn.tavg-u-hxy-lnd.day.glb` | ❌ | IFS no precip phase partition | veg |
| `atmos.prsn.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.prsn.tavg-u-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.prsn.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.prsn.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.prsnc.tavg-u-hxy-lnd.day.glb` | ❌ | No convective snow split | veg |
| `atmos.prsnsn.tavg-u-hxy-lnd.day.glb` | ❌ | IFS no snow partitioning | veg |
| `atmos.prw.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.prw.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.ps.tpt-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, extra |
| `atmos.ps.tpt-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.ps.tpt-u-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.ps.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.ps.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.psl.tpt-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.psl.tpt-u-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.psl.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.psl.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.ptp.tavg-u-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.reffclic.tavg-al-hxy-ccl.mon.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.reffclis.tavg-al-hxy-scl.mon.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.reffclwc.tavg-al-hxy-ccl.mon.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.reffclws.tavg-al-hxy-scl.mon.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.rld.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rldcs.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rlds.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, extra |
| `atmos.rlds.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.rlds.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rlds.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core, lrcs |
| `atmos.rldscs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rldscs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rls.tavg-u-hxy-u.day.glb` | ❌ | Not yet implemented | extra |
| `atmos.rls.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `atmos.rlu.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rlucs.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rlus.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.rlus.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.rlus.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rlus.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core, lrcs |
| `atmos.rluscs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rluscs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rlut.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rlut.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rlutcs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rlutcs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rsd.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsdcs.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsds.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, extra |
| `atmos.rsds.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.rsds.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core, lrcs |
| `atmos.rsds.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core, lrcs |
| `atmos.rsdscs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rsdscs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rsdscsdiff.tavg-u-hxy-u.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsdsdiff.tavg-u-hxy-u.1hr.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsdsdiff.tavg-u-hxy-u.day.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsdt.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rsdt.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rss.tavg-u-hxy-u.day.glb` | ❌ | Not yet implemented | extra |
| `atmos.rss.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `atmos.rsu.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsucs.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.rsus.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.rsus.tavg-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.rsus.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, lrcs |
| `atmos.rsus.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core, lrcs |
| `atmos.rsuscs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rsuscs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rsut.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rsut.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rsutcs.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.rsutcs.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.rtmt.tavg-u-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.sci.tavg-u-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.sfcWind.tavg-h10m-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, extra |
| `atmos.sfcWind.tavg-h10m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.sfcWind.tavg-h10m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.sftlf.ti-u-hxy-u.fx.glb` | ✅ |  | cap7, core |
| `atmos.smc.tavg-alh-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.snmsl.tavg-u-hxy-lnd.day.glb` | ❌ | HTESSEL internal - not in XIOS | veg |
| `atmos.snrefr.tavg-u-hxy-lnd.day.glb` | ❌ | HTESSEL internal - not in XIOS | veg |
| `atmos.snwc.tavg-u-hxy-lnd.day.glb` | ❌ | Not accessible via XIOS | veg |
| `atmos.ta.tpt-p6-hxy-air.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.ta.tpt-al-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.ta.tavg-700hPa-hxy-air.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.ta.tavg-al-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.tas.tpt-h2m-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.tas.tavg-h2m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core, extra |
| `atmos.tas.tavg-h2m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.tauu.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.tauv.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.tnhus.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusa.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusc.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusd.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusmp.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhuspbl.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusscp.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnhusscpbl.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnt.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tnta.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntc.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntd.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntmp.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntpbl.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntr.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntrl.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntrlcs.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntrs.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntrscs.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntscp.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.tntscpbl.tavg-al-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.ts.tavg-u-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.ts.tpt-u-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | extra |
| `atmos.ts.tpt-u-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.ts.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.ua.tpt-h100m-hxy-u.1hr.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.ua.tpt-p6-hxy-air.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.ua.tpt-al-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.ua.tavg-p19-hxy-air.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.ua.tavg-p19-hxy-air.mon.glb` | ✅ |  | cap7, core |
| `atmos.uas.tpt-h10m-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.uas.tpt-h10m-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.uas.tavg-h10m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.uas.tavg-h10m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.va.tpt-h100m-hxy-u.1hr.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.va.tpt-p6-hxy-air.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.va.tpt-al-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.va.tavg-p19-hxy-air.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.va.tavg-p19-hxy-air.mon.glb` | ✅ |  | cap7, core |
| `atmos.vas.tpt-h10m-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.vas.tpt-h10m-hxy-u.3hr.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.vas.tavg-h10m-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.vas.tavg-h10m-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `atmos.wap.tpt-p6-hxy-air.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `atmos.wap.tavg-500hPa-hxy-air.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.wap.tavg-p19-hxy-air.mon.glb` | ✅ |  | cap7, core |
| `atmos.wbgt.tavg-h2m-hxy-u.day.glb` | ❌ | Complex post-processing | extra |
| `atmos.wsg.tmax-h100m-hxy-u.1hr.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.wsg.tmax-h100m-hxy-u.mon.glb` | ❌ | IFS has 10m gust only, not 100m | extra |
| `atmos.zfull.ti-al-hxy-u.fx.glb` | ❌ | Needs IFS source code changes | cap7 |
| `atmos.zg.tpt-al-hxy-u.6hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `atmos.zg.tavg-p19-hxy-air.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `atmos.zg.tavg-p19-hxy-air.mon.glb` | ✅ |  | cap7, core |
| `atmos.ztp.tavg-u-hxy-u.mon.glb` | ❌ | Needs IFS source code changes | cap7 |

---

## Realm: atmos aerosol — 0/1 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmos.co2.tavg-al-hxy-u.mon.glb` | ❌ | No CO2 tracer in config | cap7 |

---

## Realm: atmos aerosol land — 0/2 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmos.bldep.tavg-u-hxy-u.1hr.glb` | ❌ | Needs IFS source code changes | extra |
| `atmos.bldep.tpt-u-hxy-u.3hr.glb` | ❌ | Needs IFS source code changes | veg |

---

## Realm: atmos atmosChem aerosol — 0/4 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmos.reffcclwtop.tavg-u-hxy-ccl.day.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.reffsclwtop.tavg-u-hxy-scl.day.glb` | ❌ | No cloud microphysics diagnostics | cap7 |
| `atmos.reffsclwtop.tavg-u-hxy-scl.mon.glb` | ❌ | No cloud microphysics diagnostics | veg |
| `atmos.scldncl.tavg-u-hxy-scl.day.glb` | ❌ | No cloud microphysics diagnostics | cap7 |

---

## Realm: atmos land — 1/2 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmos.areacella.ti-u-hxy-u.fx.glb` | ✅ |  | core |
| `atmos.evspsbl.tavg-u-hxy-lnd.day.glb` | ❌ | Not accessible via XIOS | extra |

---

## Realm: atmosChem — 0/9 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmosChem.cfc11.tavg-u-hm-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.cfc113.tavg-u-hm-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.cfc12.tavg-u-hm-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.ch4.tavg-p19-hxy-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.flashrate.tavg-u-hxy-u.day.glb` | ❌ | No lightning parameterization | extra |
| `atmosChem.flashrate.tavg-u-hxy-u.mon.glb` | ❌ | No lightning parameterization | extra |
| `atmosChem.hcfc22.tavg-u-hm-air.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.n2o.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.o3.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |

---

## Realm: atmosChem aerosol — 0/4 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `atmosChem.dms.tavg-al-hxy-u.mon.glb` | ❌ | No atmospheric chemistry | cap7 |
| `atmosChem.drynoy.tavg-u-hxy-u.mon.glb` | ❌ | No deposition scheme | cap7 |
| `atmosChem.emich4.tavg-u-hxy-u.mon.glb` | ❌ | No methane emission scheme | extra |
| `atmosChem.wetnoy.tavg-u-hxy-u.mon.glb` | ❌ | No deposition scheme | cap7 |

---

## Realm: land — 19/169 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `land.areacellr.ti-u-hxy-u.fx.glb` | ✅ |  | extra |
| `land.baresoilFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.baresoilFrac.tavg-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.burntFractionAll.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.c3PftFrac.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.c4PftFrac.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.cGeologicStorage.tavg-u-hxy-u.mon.glb` | ❌ | No geologic storage model | cap7 |
| `land.cLand.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cLeaf.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cLitter.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cLitterCwd.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cLitterLut.tpt-u-hxy-multi.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.cLitterSubSurf.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cLitterSurf.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cOther.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cProduct.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cProductLut.tpt-u-hxy-multi.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.cRoot.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cSoil.tavg-d100cm-hxy-lnd.mon.glb` | ❌ | No depth-resolved cSoil output | cap7 |
| `land.cSoilLut.tpt-u-hxy-multi.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.cSoilPools.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.cStem.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cVeg.tavg-u-hxy-lnd.mon.glb` | ❌ | No per-PFT output from LPJ-GUESS | cap7 |
| `land.cVegLut.tpt-u-hxy-multi.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.cropFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.cropFrac.tavg-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.cropFracC3.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.cropFracC4.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.dcw.tavg-u-hxy-lnd.day.glb` | ❌ | Not yet implemented | extra |
| `land.dgw.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.drivw.tavg-u-hxy-lnd.day.glb` | ❌ | No river routing model | veg |
| `land.dslw.tavg-u-hxy-lnd.day.glb` | ❌ | Not yet implemented | extra |
| `land.dsn.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.dsw.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.esn.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.evspsblpot.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.evspsblpot.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.evspsblsoi.tavg-u-hxy-u.3hr.glb` | ❌ | Internal HTESSEL - not in XIOS | veg |
| `land.evspsblsoi.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.evspsblveg.tavg-u-hxy-u.3hr.glb` | ❌ | Internal HTESSEL - not in XIOS | veg |
| `land.evspsblveg.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.fAnthDisturb.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fBNF.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fCLandToOcean.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fDeforestToAtmos.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fDeforestToProduct.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fFire.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fFireAll.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fFireNat.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fHarvestToAtmos.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fHarvestToGeologicStorage.tavg-u-hxy-lnd.mon.glb` | ❌ | No geologic storage model | cap7 |
| `land.fHarvestToProduct.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fLitterFire.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fLitterSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fLuc.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fLulccAtmLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNLandToOcean.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNLitterSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNVegSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNgas.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNgasFire.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNleach.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNloss.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fNup.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fProductDecomp.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fVegFire.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fVegLitter.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.fVegLitterMortality.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fVegLitterSenescence.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fVegSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fVegSoilMortality.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fVegSoilSenescence.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.fracInLut.tsum-u-hxy-lnd.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fracLut.tpt-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fracLut.tpt-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.fracOutLut.tsum-u-hxy-lnd.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.gpp.tavg-u-hxy-lnd.mon.glb` | ❌ | No per-PFT output from LPJ-GUESS | cap7 |
| `land.gppLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.gppVgt.tavg-u-hxy-multi.day.glb` | ❌ | No daily per-PFT from LPJ-GUESS | veg |
| `land.grassFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.grassFrac.tavg-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.hfdsl.tavg-u-hxy-lnd.3hr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.hflsLut.tavg-u-hxy-multi.mon.glb` | ❌ | Energy balance var - not per-tile | veg |
| `land.hfssLut.tavg-u-hxy-multi.mon.glb` | ❌ | Energy balance var - not per-tile | veg |
| `land.irrDem.tavg-u-hxy-u.day.glb` | ❌ | No irrigation scheme | extra |
| `land.irrGw.tavg-u-hxy-u.day.glb` | ❌ | No irrigation scheme | extra |
| `land.irrLut.tavg-u-hxy-u.day.glb` | ❌ | No irrigation scheme | extra |
| `land.irrLut.tavg-u-hxy-multi.mon.glb` | ❌ | No irrigation scheme | veg |
| `land.irrSurf.tavg-u-hxy-u.day.glb` | ❌ | No irrigation scheme | extra |
| `land.lai.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | extra |
| `land.lai.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.laiLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.laiVgt.tavg-u-hxy-multi.day.glb` | ❌ | No daily per-PFT from LPJ-GUESS | veg |
| `land.landCoverFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.mrro.tavg-u-hxy-lnd.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `land.mrro.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `land.mrro.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.mrrob.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.mrros.tavg-u-hxy-lnd.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `land.mrros.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.mrso.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `land.mrso.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.mrsofc.ti-u-hxy-lnd.fx.glb` | ✅ |  | cap7, core |
| `land.mrsol.tavg-d100cm-hxy-lnd.3hr.glb` | ❌ | Only mon frequency implemented | veg |
| `land.mrsol.tavg-d10cm-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `land.mrsol.tavg-d10cm-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `land.mrsolLut.tavg-d10cm-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.mrsow.tavg-u-hxy-lnd.day.glb` | ❌ | Not yet implemented | extra |
| `land.mrtws.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nLand.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nLitter.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nMineral.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nProduct.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nVeg.tavg-u-hxy-lnd.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nbp.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.nbpLut.tavg-u-hxy-multi.mon.glb` | ❌ | No per-tile variant | veg |
| `land.nep.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.npp.tavg-u-hxy-lnd.mon.glb` | ❌ | No per-PFT output from LPJ-GUESS | cap7 |
| `land.nppLeaf.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.nppLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.nppOther.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.nppRoot.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.nppStem.tavg-u-hxy-lnd.mon.glb` | ❌ | No LPJ-GUESS output file | cap7 |
| `land.nppVgt.tavg-u-hxy-multi.day.glb` | ❌ | No daily per-PFT from LPJ-GUESS | veg |
| `land.orog.ti-u-hxy-u.fx.glb` | ✅ |  | cap7, core, extra |
| `land.pastureFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.pastureFracC3.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.pastureFracC4.tavg-u-hxy-u.mon.glb` | ✅ |  | extra |
| `land.prveg.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.qgwr.tavg-u-hxy-lnd.day.glb` | ❌ | No groundwater scheme | veg |
| `land.ra.tavg-u-hxy-lnd.mon.glb` | ❌ | No per-PFT output from LPJ-GUESS | cap7 |
| `land.raLeaf.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.raLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.raOther.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.raRoot.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.raStem.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.raVgt.tavg-u-hxy-multi.day.glb` | ❌ | No daily per-PFT from LPJ-GUESS | veg |
| `land.residualFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.rh.tavg-u-hxy-lnd.mon.glb` | ❌ | No per-PFT output from LPJ-GUESS | cap7 |
| `land.rhLitter.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.rhLut.tavg-u-hxy-multi.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.rhSoil.tavg-u-hxy-lnd.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.rhVgt.tavg-u-hxy-multi.day.glb` | ❌ | No daily per-PFT from LPJ-GUESS | veg |
| `land.rivi.tavg-u-hxy-lnd.day.glb` | ❌ | No river routing model | extra |
| `land.rivo.tavg-u-hxy-lnd.day.glb` | ❌ | No river routing model | veg |
| `land.rootd.ti-u-hxy-lnd.fx.glb` | ✅ |  | cap7, core |
| `land.rzwc.tavg-u-hxy-lnd.day.glb` | ❌ | HTESSEL layers not root-zone-depth | extra |
| `land.sftgif.ti-u-hxy-u.fx.glb` | ✅ |  | cap7, core |
| `land.shrubFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.shrubFrac.tavg-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.slthick.ti-sl-hxy-lnd.fx.glb` | ✅ |  | cap7, core |
| `land.srfrad.tavg-u-hxy-u.3hr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.sw.tavg-u-hxy-lnd.day.glb` | ❌ | No surface water scheme | veg |
| `land.sweLut.tavg-u-hxy-multi.mon.glb` | ❌ | No per-tile variant | veg |
| `land.tas.tavg-h2m-hxy-u.1hr.glb` | ❌ | Only mon frequency implemented | cap7, extra |
| `land.tasLut.tavg-h2m-hxy-multi.mon.glb` | ❌ | Atmospheric var - not per-tile | veg |
| `land.tran.tavg-u-hxy-u.3hr.glb` | ❌ | FullPos field not accessible | veg |
| `land.tran.tavg-u-hxy-lnd.mon.glb` | ❌ | Internal HTESSEL - not in XIOS | cap7 |
| `land.treeFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.treeFrac.tavg-u-hxy-u.yr.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.treeFracBdlDcd.tavg-u-hxy-u.mon.glb` | ❌ | Veg-only variable, not yet implemented | veg |
| `land.tsLut.tavg-u-hxy-multi.mon.glb` | ❌ | No Lut tile variant | veg |
| `land.tsl.tavg-sl-hxy-lnd.mon.glb` | ❌ | Needs new custom step (per-layer) | cap7 |
| `land.tslsi.tpt-u-hxy-lsi.3hr.glb` | ❌ | Needs new custom step (per-layer) | veg |
| `land.tslsi.tavg-u-hxy-lsi.day.glb` | ❌ | Needs new custom step (per-layer) | cap7 |
| `land.vegFrac.tavg-u-hxy-u.mon.glb` | ❌ | Not yet implemented | cap7 |
| `land.vegHeight.tavg-u-hxy-tree.mon.glb` | ❌ | Only tree-only variant in LPJ | veg |
| `land.wtd.tavg-u-hxy-lnd.day.glb` | ❌ | No groundwater scheme | veg |

---

## Realm: landIce — 0/2 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `landIce.sbl.tavg-u-hxy-u.day.glb` | ❌ | Not accessible via IFS/FESOM | veg |
| `landIce.sbl.tavg-u-hxy-u.mon.glb` | ❌ | Not accessible via IFS/FESOM | cap7, lrcs, veg |

---

## Realm: landIce land — 4/18 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `landIce.agesno.tavg-u-hxy-lnd.mon.glb` | ❌ | No snow age tracer | veg |
| `landIce.hfdsn.tavg-u-hxy-lnd.day.glb` | ❌ | Not standard IFS/FESOM output | veg |
| `landIce.hfdsn.tavg-u-hxy-lnd.mon.glb` | ❌ | Not standard IFS/FESOM output | veg |
| `landIce.lwsnl.tavg-u-hxy-lnd.day.glb` | ❌ | Single-layer snow - no liquid water | veg |
| `landIce.lwsnl.tavg-u-hxy-lnd.mon.glb` | ❌ | Single-layer snow - no liquid water | veg |
| `landIce.mrfso.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `landIce.pflw.tavg-u-hxy-lnd.day.glb` | ❌ | No permafrost scheme | veg |
| `landIce.pflw.tavg-u-hxy-lnd.mon.glb` | ❌ | No permafrost scheme | veg |
| `landIce.snc.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `landIce.snc.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `landIce.snd.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `landIce.snm.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | veg |
| `landIce.snw.tavg-u-hxy-lnd.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `landIce.snw.tavg-u-hxy-lnd.mon.glb` | ✅ |  | cap7, core |
| `landIce.sootsn.tavg-u-hxy-lnd.mon.glb` | ❌ | Needs CAMS aerosol deposition | veg |
| `landIce.tpf.tavg-u-hxy-lnd.day.glb` | ❌ | No permafrost scheme | veg |
| `landIce.tpf.tavg-u-hxy-lnd.mon.glb` | ❌ | No permafrost scheme | veg |
| `landIce.tsn.tavg-u-hxy-lnd.day.glb` | ❌ | Veg-only variable, not yet implemented | veg |

---

## Realm: ocean — 58/153 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `ocean.absscint.tavg-op4-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.agessc.tavg-ol-hxy-sea.mon.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.areacello.ti-u-hxy-u.fx.glb` | ✅ |  | cap7, core |
| `ocean.basin.ti-u-hxy-u.fx.glb` | ❌ | Cannot derive - needs external mask | cap7, core |
| `ocean.bigthetao.tavg-ol-hxy-sea.dec.glb` | ❌ | FESOM uses potential temp, not cons. | lrcs |
| `ocean.bigthetao.tavg-ol-hxy-sea.mon.glb` | ❌ | FESOM uses potential temp, not cons. | cap7, core, lrcs |
| `ocean.chcint.tavg-op4-hxy-sea.mon.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.deptho.ti-u-hxy-sea.fx.glb` | ✅ |  | cap7, core |
| `ocean.difmxybo.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.difmxylo.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.diftrblo.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.diftrelo.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.difvho.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.difvso.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.dispkexyfo.tavg-u-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dxto.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dxuo.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dxvo.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dyto.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dyuo.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.dyvo.ti-u-hxy-u.fx.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ficeberg.tavg-ol-hxy-sea.mon.glb` | ❌ | No iceberg model | cap7, lrcs |
| `ocean.flandice.tavg-u-hxy-sea.mon.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.friver.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7 |
| `ocean.hfacrossline.tavg-u-ht-sea.mon.glb` | ❌ | No strait diagnostics | lrcs |
| `ocean.hfbasin.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | cap7 |
| `ocean.hfbasinpadv.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.hfbasinpmadv.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.hfbasinpmdiff.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.hfbasinpsmadv.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.hfds.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.hfevapds.tavg-u-hxy-ifs.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.hfgeou.ti-u-hxy-sea.fx.glb` | ❌ | Not implemented in FESOM2 | cap7, core |
| `ocean.hfgeou.tavg-u-hxy-sea.mon.glb` | ❌ | Not implemented in FESOM2 | lrcs |
| `ocean.hfibthermds.tavg-ol-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.hfrainds.tavg-u-hxy-ifs.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.hfrunoffds.tavg-ol-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.hfsnthermds.tavg-ol-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.hfx.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.hfx.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7 |
| `ocean.hfy.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.hfy.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7 |
| `ocean.htovgyre.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.htovovrt.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.masscello.tavg-ol-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.masscello.ti-ol-hxy-sea.fx.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `ocean.masscello.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.masso.tavg-u-hm-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.masso.tavg-u-hm-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.mfo.tavg-u-ht-sea.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `ocean.mlotst.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.mlotst.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core, lrcs |
| `ocean.mlotstsq.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.msftbarot.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.msftm.tavg-ol-hyb-sea.mon.glb` | ❌ | Basin masks needed | cap7, lrcs |
| `ocean.msftmmpa.tavg-ol-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.msftmsmpa.tavg-ol-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.msfty.tavg-ol-ht-sea.mon.glb` | ❌ | Basin masks needed | cap7, lrcs |
| `ocean.msftypa.tavg-ol-ht-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.obvfsq.tavg-ol-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.ocontempdiff.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontempmint.tavg-u-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontemppadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontemppmdiff.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontemppsmadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontemprmadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.ocontemptend.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.opottempdiff.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.opottempmint.tavg-u-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.opottemppadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.opottemppmdiff.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.opottemppsmadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.opottemprmadvect.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.opottemptend.tavg-ol-hxy-sea.dec.glb` | ❌ | Only yr frequency implemented | lrcs |
| `ocean.opottemptend.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.osaltdiff.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.osaltpadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.osaltpmdiff.tavg-ol-hxy-sea.yr.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.osaltpsmadvect.tavg-ol-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.osaltpsmadvect.tavg-ol-hxy-sea.yr.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.osaltrmadvect.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.osalttend.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.pbo.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.pfscint.tavg-op4-hxy-sea.mon.glb` | ❌ | Not in namelist.io | lrcs |
| `ocean.phcint.tavg-op4-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.pso.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.rsdoabsorb.tavg-ol-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.scint.tavg-op4-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.sf6.tavg-ol-hxy-sea.mon.glb` | ❌ | No SF6 tracer | cap7 |
| `ocean.sfacrossline.tavg-u-ht-sea.mon.glb` | ❌ | No strait diagnostics | lrcs |
| `ocean.sfriver.tavg-u-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.sftof.ti-u-hxy-u.fx.glb` | ✅ |  | cap7, core |
| `ocean.sfx.tavg-ol-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.sfy.tavg-ol-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.sltbasin.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.sltovgyre.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.sltovovrt.tavg-u-hyb-sea.mon.glb` | ❌ | Basin masks needed | lrcs |
| `ocean.so.tavg-ol-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.so.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core, lrcs |
| `ocean.sob.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.somint.tavg-u-hxy-sea.yr.glb` | ✅ |  | lrcs |
| `ocean.sos.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `ocean.sos.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core, lrcs |
| `ocean.sossq.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.sw17O.tavg-ol-hxy-sea.mon.glb` | ❌ | No isotope physics | lrcs |
| `ocean.sw18O.tavg-ol-hxy-sea.mon.glb` | ❌ | No isotope physics | lrcs |
| `ocean.sw2H.tavg-ol-hxy-sea.mon.glb` | ❌ | No isotope physics | lrcs |
| `ocean.tauuo.tavg-u-hxy-sea.3hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `ocean.tauuo.tavg-u-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.tauuo.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.tauvo.tavg-u-hxy-sea.3hr.glb` | ❌ | Only mon frequency implemented | cap7 |
| `ocean.tauvo.tavg-u-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.tauvo.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.thetao.tavg-op20bar-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.thetao.tavg-ol-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.thetao.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core, lrcs |
| `ocean.thkcello.tavg-ol-hxy-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.thkcello.ti-ol-hxy-sea.fx.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `ocean.thkcello.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.thkcelluo.tavg-ol-hxy-sea.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `ocean.thkcellvo.tavg-ol-hxy-sea.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `ocean.tnkebto.tavg-u-hxy-sea.yr.glb` | ❌ | Not output by FESOM | lrcs |
| `ocean.tnpeo.tavg-u-hxy-sea.yr.glb` | ❌ | Not output by FESOM | lrcs |
| `ocean.tob.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.tos.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `ocean.tos.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core, lrcs |
| `ocean.tossq.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `ocean.tossq.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.umo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.uo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.uos.tavg-u-hxy-sea.day.glb` | ✅ |  | lrcs |
| `ocean.vmo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.vo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.volcello.tavg-ol-hxy-sea.dec.glb` | ❌ | Decadal frequency not implemented | lrcs |
| `ocean.volcello.ti-ol-hxy-sea.fx.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.volcello.tavg-ol-hxy-sea.mon.glb` | ❌ | Not yet implemented | cap7 |
| `ocean.volcello.tavg-ol-hxy-sea.yr.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.volo.tavg-u-hm-sea.dec.glb` | ❌ | Only mon frequency implemented | lrcs |
| `ocean.volo.tavg-u-hm-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.vos.tavg-u-hxy-sea.day.glb` | ✅ |  | lrcs |
| `ocean.vsf.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.vsfcorr.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.vsfevap.tavg-u-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.vsfpr.tavg-u-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.vsfriver.tavg-u-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.wfcorr.tavg-u-hxy-sea.mon.glb` | ❌ | Not yet implemented | lrcs |
| `ocean.wfo.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.wmo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.wo.tavg-ol-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.zos.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `ocean.zos.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `ocean.zossq.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.zostoga.tavg-u-hm-sea.mon.glb` | ✅ |  | cap7, core |

---

## Realm: ocean seaIce — 3/3 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `ocean.sfdsi.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.siflfwbot.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `ocean.vsfsit.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |

---

## Realm: seaIce — 40/91 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `seaIce.evspsbl.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7, core, lrcs |
| `seaIce.prra.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7 |
| `seaIce.siage.tavg-u-hxy-si.day.glb` | ❌ | tr_iage=.false., not enabled | lrcs |
| `seaIce.siage.tavg-u-hxy-si.mon.glb` | ❌ | tr_iage=.false., not enabled | lrcs |
| `seaIce.siarea.tavg-u-hm-u.day.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.siarea.tavg-u-hm-u.mon.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.siareaacrossline.tavg-u-ht-u.mon.glb` | ❌ | No strait diagnostics | lrcs |
| `seaIce.sicompstren.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siconc.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | cap7, core |
| `seaIce.siconc.tavg-u-hxy-u.mon.glb` | ✅ |  | cap7, core |
| `seaIce.siconca.tavg-u-hxy-u.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `seaIce.siconca.tavg-u-hxy-u.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidconcdyn.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidconcth.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidivvel.tpt-u-hxy-si.mon.glb` | ❌ | Needs spatial derivatives | lrcs |
| `seaIce.sidmassdyn.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidmassgrowthbot.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassgrowthsi.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassgrowthwat.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassmeltbot.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassmeltlat.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassmelttop.tavg-u-hxy-si.mon.glb` | ❌ | No split growth/melt terms | lrcs |
| `seaIce.sidmassth.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidmasstranx.tavg-u-hxy-u.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidmasstrany.tavg-u-hxy-u.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidragbot.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sidragtop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sieqthick.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7 |
| `seaIce.siextent.tavg-u-hm-u.day.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.siextent.tavg-u-hm-u.mon.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.sifb.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siflcondbot.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siflcondtop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siflfwdrain.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sifllattop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siflsensbot.tavg-u-hxy-si.mon.glb` | ❌ | Ocean-ice interface flux not output | lrcs |
| `seaIce.siflsenstop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.siflswdbot.tavg-u-hxy-si.mon.glb` | ❌ | Transmitted SW flux not output | lrcs |
| `seaIce.siforcecoriolx.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.siforcecorioly.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.siforceintstrx.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.siforceintstry.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.siforcetiltx.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.siforcetilty.tavg-u-hxy-si.mon.glb` | ❌ | Not output by FESOM | lrcs |
| `seaIce.sihc.tavg-u-hxy-sea.mon.glb` | ✅ |  | lrcs |
| `seaIce.siitdconc.tavg-u-hxy-si.mon.glb` | ❌ | Single-category ice - no ITD | lrcs |
| `seaIce.siitdsnconc.tavg-u-hxy-si.day.glb` | ❌ | Single-category ice - no ITD | veg |
| `seaIce.siitdsnconc.tavg-u-hxy-si.mon.glb` | ❌ | Single-category ice - no ITD | lrcs |
| `seaIce.siitdsnthick.tavg-u-hxy-si.day.glb` | ❌ | Single-category ice - no ITD | veg |
| `seaIce.siitdsnthick.tavg-u-hxy-si.mon.glb` | ❌ | Single-category ice - no ITD | lrcs |
| `seaIce.siitdthick.tavg-u-hxy-si.mon.glb` | ❌ | Single-category ice - no ITD | lrcs |
| `seaIce.simass.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7, core |
| `seaIce.simassacrossline.tavg-u-ht-u.mon.glb` | ❌ | No strait diagnostics | lrcs |
| `seaIce.simpconc.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.simpeffconc.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.simprefrozen.tavg-u-hxy-simp.mon.glb` | ✅ |  | lrcs |
| `seaIce.simpthick.tavg-u-hxy-simp.mon.glb` | ✅ |  | lrcs |
| `seaIce.sirdgconc.tavg-u-hxy-si.mon.glb` | ❌ | tr_lvl=.false., no ridging tracer | lrcs |
| `seaIce.sisali.tavg-u-hxy-si.mon.glb` | ❌ | Single-category sea ice | cap7 |
| `seaIce.sisaltmass.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sishearvel.tpt-u-hxy-si.mon.glb` | ❌ | Needs spatial derivatives | lrcs |
| `seaIce.sisndmassdyn.tavg-u-hxy-si.mon.glb` | ❌ | Not yet implemented | lrcs |
| `seaIce.sisndmasssi.tavg-u-hxy-si.mon.glb` | ❌ | Not yet implemented | lrcs |
| `seaIce.sisndmasswind.tavg-u-hxy-si.mon.glb` | ❌ | Not yet implemented | lrcs |
| `seaIce.sisnhc.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | veg |
| `seaIce.sisnhc.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sisnmass.tavg-u-hm-si.day.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.sisnmass.tavg-u-hm-si.mon.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.sisnmassacrossline.tavg-u-ht-u.mon.glb` | ❌ | No strait diagnostics | lrcs |
| `seaIce.sispeed.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `seaIce.sispeed.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistressave.tpt-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistressmax.tpt-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistrxdtop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistrxubot.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistrydtop.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sistryubot.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sitempbot.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.sitempsnic.tavg-u-hxy-si.day.glb` | ❌ | No snow-ice interface temp | veg |
| `seaIce.sitempsnic.tavg-u-hxy-si.mon.glb` | ❌ | No snow-ice interface temp | cap7 |
| `seaIce.sitimefrac.tavg-u-hxy-sea.day.glb` | ❌ | Only mon frequency implemented | lrcs |
| `seaIce.sitimefrac.tavg-u-hxy-sea.mon.glb` | ✅ |  | cap7, core |
| `seaIce.siu.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `seaIce.siu.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7, core |
| `seaIce.siv.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `seaIce.siv.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7, core |
| `seaIce.sivol.tavg-u-hm-u.day.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.sivol.tavg-u-hm-u.mon.nh` | ❌ | Not yet implemented | lrcs |
| `seaIce.snd.tavg-u-hxy-sn.day.glb` | ❌ | Only mon frequency implemented | cap7, veg |
| `seaIce.snm.tavg-u-hxy-si.mon.glb` | ✅ |  | lrcs |
| `seaIce.ts.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | lrcs, veg |

---

## Realm: seaIce ocean — 1/2 rules

| Variable | Rule | Reason | Categories |
|---|---|---|---|
| `seaIce.sithick.tavg-u-hxy-si.day.glb` | ❌ | Only mon frequency implemented | cap7 |
| `seaIce.sithick.tavg-u-hxy-si.mon.glb` | ✅ |  | cap7, core, lrcs |

---

