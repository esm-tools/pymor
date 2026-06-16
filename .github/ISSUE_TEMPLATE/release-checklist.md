---
name: Release checklist
about: Checklist for cutting a new pycmor release
title: "Release vX.Y.Z"
labels: release
assignees: ''
---

## Pre-release

- [ ] All planned PRs merged
- [ ] `CHANGELOG` / release notes up to date
- [ ] `version` in `CITATION.cff` and `codemeta.json` matches the new version
- [ ] `date-released` in `CITATION.cff` updated

## Release

- [ ] Tag pushed / GitHub Release created
- [ ] Zenodo DOI auto-generated (check https://zenodo.org — linked via `.zenodo.json` or GitHub integration)
- [ ] Update `doi` in `CITATION.cff` and `identifier[doi]` in `codemeta.json` with the new Zenodo DOI

## Post-release: Software Heritage SWHID

The GitHub Actions workflow triggers an SWH archival request automatically.
After ~1 hour, run the helper script to fetch the new SWHID and update the files:

```bash
python scripts/update_swhid.py
# Follow the output — it will print the SWHID and patch CITATION.cff + codemeta.json
```

Then open a PR with the updated files.

- [ ] `identifiers[swh]` in `CITATION.cff` updated with new SWHID
- [ ] `identifier[swh]` in `codemeta.json` updated with new SWHID
- [ ] SWHID also updated in the Helmholtz RSD: https://helmholtz.software/software/pycmor/edit/software-heritage

## Done

- [ ] Release announcement (if applicable)
