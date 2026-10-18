"""Compatibility import for the shared MolStat workflow processor."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from molstat._statistics.patolog_flow import *
