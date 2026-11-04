"""Rebuild the run index (maintainer), then commit index/runs.jsonl.

    python -m tools.build_index                    # DATA_ROOT from config.yaml
    python -m tools.build_index --data-root /mnt/share/my_campaign/data

Run from the repo root. In WSL, mount the share read-only first, e.g.
    sudo mount -t drvfs S: /mnt/share -o ro
A dropped VPN or network connection makes SQLite report a database as malformed;
check the connection and rerun before suspecting the file. Only reads the
databases; writes nothing but index/runs.jsonl.
"""

import argparse

from wynaut.index import build_index
from wynaut.paths import INDEX_PATH

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-root", help="folder with the .db files (default: DATA_ROOT)")
    args = parser.parse_args()
    if args.data_root:
        data_root = args.data_root
    else:
        from wynaut.paths import DATA_ROOT
        data_root = DATA_ROOT

    print(f"indexing {data_root}")
    report = build_index(data_root)
    print(f"\nwrote {report['total_runs']} runs to {INDEX_PATH}")
    print(f"excluded: {report['excluded']}")
    for db, err in report["failed"].items():
        print(f"FAILED {db}: {err}")
    if report["duplicate_guids"]:
        print(f"WARNING: {len(report['duplicate_guids'])} runs share a guid with "
              f"another run, e.g. {report['duplicate_guids'][:3]}")
