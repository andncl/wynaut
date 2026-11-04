"""Export averaged copies of new runs (maintainer): python tools/export_averaged.py

Run after build_index.py when new data arrives. See wynaut/averaged.py.
"""

from wynaut.averaged import export_averaged

if __name__ == "__main__":
    export_averaged()
