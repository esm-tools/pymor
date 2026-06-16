#!/usr/bin/env python3
"""
Fetch the latest Software Heritage snapshot SWHID for pycmor and update
CITATION.cff and codemeta.json in-place.

Usage:
    python scripts/update_swhid.py

Run this after a release, once the SWH archival is complete (~1 hour after tag push).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ORIGIN = "https://github.com/esm-tools/pycmor"
SWH_API = "https://archive.softwareheritage.org/api/1"
REPO_ROOT = Path(__file__).parent.parent


def get_latest_swhid() -> str:
    url = f"{SWH_API}/origin/{ORIGIN}/visit/latest/?require_snapshot=true"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        sys.exit(f"Failed to fetch latest SWH visit: {e}\n"
                 f"Is the repository archived? Check: "
                 f"https://archive.softwareheritage.org/browse/origin/?origin_url={ORIGIN}")

    snapshot = data.get("snapshot")
    if not snapshot:
        sys.exit("Latest SWH visit has no snapshot yet — archival may still be in progress. "
                 "Try again in a few minutes.")

    return f"swh:1:snp:{snapshot}"


def update_citation_cff(swhid: str) -> None:
    path = REPO_ROOT / "CITATION.cff"
    content = path.read_text()

    # Replace existing swh identifier value
    pattern = r'(- type: swh\s+value: ")[^"]+"'
    replacement = rf'\g<1>{swhid}"'
    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print("WARNING: could not find '- type: swh' block in CITATION.cff — "
              "please update identifiers.swh manually.")
        print(f"  SWHID to add: {swhid}")
        return

    path.write_text(new_content)
    print(f"Updated CITATION.cff: identifiers.swh = {swhid}")


def update_codemeta(swhid: str) -> None:
    path = REPO_ROOT / "codemeta.json"
    data = json.loads(path.read_text())

    identifiers = data.get("identifier", [])
    if isinstance(identifiers, str):
        identifiers = [{"@type": "PropertyValue", "propertyID": "doi", "value": identifiers}]

    updated = False
    for entry in identifiers:
        if isinstance(entry, dict) and entry.get("propertyID") == "swh":
            entry["value"] = swhid
            updated = True
            break

    if not updated:
        identifiers.append({"@type": "PropertyValue", "propertyID": "swh", "value": swhid})

    data["identifier"] = identifiers
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated codemeta.json: identifier[swh] = {swhid}")


def main() -> None:
    print(f"Fetching latest Software Heritage snapshot for {ORIGIN} ...")
    swhid = get_latest_swhid()
    print(f"SWHID: {swhid}\n")

    update_citation_cff(swhid)
    update_codemeta(swhid)

    print("\nDone. Next steps:")
    print("  1. git diff  # review the changes")
    print("  2. git add CITATION.cff codemeta.json && git commit -m 'chore: update SWHID for release'")
    print("  3. Open a PR or push directly to main")
    print(f"  4. Update the Helmholtz RSD: "
          f"https://helmholtz.software/software/pycmor/edit/software-heritage")


if __name__ == "__main__":
    main()
