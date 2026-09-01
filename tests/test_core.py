"""Lightweight sanity checks for the pure-logic core modules.

Run: python -m pytest tests/  (or: python tests/test_core.py)
No network, no API keys needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.file_size_formatter import format_file_size  # noqa: E402
from core.title_cleaner import clean_title  # noqa: E402


def test_file_size():
    assert format_file_size(0) is None
    assert format_file_size(None) is None
    assert format_file_size(1_500_000_000) == "1.40 GB"
    assert format_file_size(700 * 1024 * 1024) == "700 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.00 GB"


def test_title_cleaner_basic():
    r = clean_title("Tekken 5 (USA) [PS2].iso")
    assert r.title == "Tekken 5"
    assert r.region_tag == "usa"
    assert r.disc_number is None


def test_title_cleaner_disc_and_region():
    r = clean_title("Final Fantasy VII (Disc 1) (USA).bin")
    assert r.title == "Final Fantasy VII"
    assert r.region_tag == "usa"
    assert r.disc_number == "Disc 1"


def test_title_cleaner_no_region_defaults_none():
    r = clean_title("Some Obscure Game.7z")
    assert r.title == "Some Obscure Game"
    assert r.region_tag is None


def test_title_cleaner_europe_and_chained_ext():
    r = clean_title("Gran Turismo 4 [Europe].iso.zip")
    assert r.title == "Gran Turismo 4"
    assert r.region_tag == "europe"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
