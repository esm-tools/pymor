# Branch Reorganization Plan

## Overview

The `future/accessors` branch contains 34 commits mixing 4 orthogonal concepts that should be separated into independent, reviewable features.

## Current State

- **`future/accessors`** - Mixed experimental branch with 4 distinct concepts intertwined

## Target Structure

```
prep-release (base)
    │
    ├── future/work (rename from future/accessors)
    │   └── "Mixed experimental branch - DO NOT MERGE AS-IS"
    │       └── Contains all 34 commits in current state
    │
    └── future/main (NEW branch from prep-release)
        └── "Clean integration branch - this is what the future looks like"
            │
            ├── future/feat/xarray-accessor
            │   └── Cherry-pick: Accessor API commits (Concept 1)
            │
            ├── future/refactor/test-fixtures
            │   └── Cherry-pick: Test modernization commits (Concept 2)
            │
            ├── future/feat/plugin-system
            │   └── Cherry-pick: BaseModelRun + entry points (Concept 3)
            │
            └── future/fix/ci-maintenance
                └── Cherry-pick: Bug fixes (Concept 4)
```

## The Four Concepts

### Concept 1: Xarray Accessor API ⭐ (Primary Feature)

**What**: Add `ds.pycmor.process(compound_name)` interface

**Commits to cherry-pick:**
- 249675f - wip: ...and the mother-f#%^ing kitchen sink
- 0efab5d - fix: correct test_accessors to use data_request_variable properly
- ec2f837 - feat: add inherit section support for accessor defaults
- ea06bf1 - wip: guardrail import of accessor functionality

**Why**: User-facing feature - cleaner API for processing datasets

---

### Concept 2: Test Infrastructure Modernization 🔧

**What**: Reorganize test fixtures with modern patterns

**Commits to cherry-pick:**
- c8224ee - Refactor test fixtures to model-centric structure and fix deprecation warnings
- bcb0e35 - refactor: add semantic fixture naming with deprecation warnings
- cd97d49 - refactor: migrate sample_rules fixtures to use new datadir naming
- df5a1b3 - test: lazy import numpy for fesom fake mesh
- 006908b - test: clean up some imports in fixtures
- a686fee - test: better fixture for filecache - lazy imports
- Plus assorted "wip" commits related to fixture refactoring

**Why**: Technical debt cleanup - fixtures were messy and hard to maintain

---

### Concept 3: Plugin System for Model Contributions 🔌

**What**: Entry point-based plugin architecture

**Commits to cherry-pick:**
- 5269aff - Refactor fesom_uxarray fixtures to use BaseModelRun pattern
- 9cadb9e - Refactor awicm_recom and fesom_2p6_pimesh to use BaseModelRun pattern
- 337bc10 - Add plugin system for external model contributions
- 47439b9 - Register built-in models via entry points
- 1206b24 - Rename entry point and update docs with realistic examples
- e452c4a - Add POEM (Potsdam Earth Model) as third plugin example

**Why**: Extensibility - external packages can contribute model fixtures

---

### Concept 4: Bug Fixes & CI Maintenance 🐛

**What**: Keep things working

**Commits to cherry-pick:**
- 99f2a58 - enables ci for prototype branches
- 6e4ae6c - Refactor doctest sanity check to use actual doctests
- ed4f7cf - Add activity_id to all test configurations
- Assorted "wip" commits for bug fixes

**Why**: Necessary maintenance discovered during development

---

## Execution Steps

### Step 1: Rename current branch
```bash
git branch -m future/accessors future/work
git push origin future/work
git push origin --delete future/accessors
```

### Step 2: Create clean integration branch
```bash
git checkout prep-release
git checkout -b future/main
git push -u origin future/main
```

### Step 3: Create feature branches

#### 3a. Xarray Accessor
```bash
git checkout future/main
git checkout -b future/feat/xarray-accessor
# Cherry-pick commits from Concept 1
git cherry-pick 249675f 0efab5d ec2f837 ea06bf1
git push -u origin future/feat/xarray-accessor
```

#### 3b. Test Fixtures
```bash
git checkout future/main
git checkout -b future/refactor/test-fixtures
# Cherry-pick commits from Concept 2
git cherry-pick c8224ee bcb0e35 cd97d49 df5a1b3 006908b a686fee
git push -u origin future/refactor/test-fixtures
```

#### 3c. Plugin System
```bash
git checkout future/main
git checkout -b future/feat/plugin-system
# Cherry-pick commits from Concept 3
git cherry-pick 5269aff 9cadb9e 337bc10 47439b9 1206b24 e452c4a
git push -u origin future/feat/plugin-system
```

#### 3d. CI Maintenance
```bash
git checkout future/main
git checkout -b future/fix/ci-maintenance
# Cherry-pick commits from Concept 4
git cherry-pick 99f2a58 6e4ae6c ed4f7cf
git push -u origin future/fix/ci-maintenance
```

### Step 4: Test each feature branch independently

Run CI on each feature branch to ensure they work independently.

### Step 5: Merge into future/main

Merge completed, tested feature branches into `future/main` in logical order:

1. `future/fix/ci-maintenance` (foundation fixes)
2. `future/refactor/test-fixtures` (infrastructure)
3. `future/feat/plugin-system` (requires test infrastructure)
4. `future/feat/xarray-accessor` (primary feature)

### Step 6: Release preparation

When `future/main` is ready, merge into `prep-release` for the next release.

---

## Benefits

- **`future/work`**: Preserved history of all experimental work (archived, not deleted)
- **`future/main`**: Clean, reviewable, organized feature integration
- **Feature branches**: Independent, testable, mergeable units
- **Git history**: Logical, bisectable, understandable
- **Code review**: Each concept can be reviewed independently

---

## Notes

- **DO NOT delete `future/work`** - it's the source of truth for all experimental commits
- Cherry-picking may require conflict resolution
- Some commits may need to be squashed or split during cherry-picking
- Feature branches should be tested independently before merging to `future/main`
- This plan assumes CI passes on current `future/accessors` (soon to be `future/work`)

## Status

⏳ **Waiting for CI to pass on current `future/accessors` branch before executing**

Current CI run: https://github.com/esm-tools/pycmor/actions
