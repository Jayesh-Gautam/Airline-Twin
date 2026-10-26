"""Shared fixtures: one Spark session and one generated sample dataset
(make_sample_data.py) for the whole test run."""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import make_sample_data as S  # noqa: E402
from spark_session import get_spark  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    s = get_spark(app_name="airline-tests", driver_memory="2g")
    s.conf.set("spark.sql.shuffle.partitions", "4")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def sample_dirs(tmp_path_factory):
    """(clean_dir, dirty_dir) written by make_sample_data."""
    base = tmp_path_factory.mktemp("sample")
    clean = S.build(n_instances=120)
    S.write(clean, str(base / "sample"))
    S.write(S.make_dirty(clean), str(base / "sample-dirty"))
    return str(base / "sample"), str(base / "sample-dirty")


@pytest.fixture(scope="session")
def cleaned_dirty(spark, sample_dirs):
    """Full clean_all() result on the dirty sample: (tables, dq_report, rule_stats)."""
    from pipeline import clean
    return clean.clean_all(spark, sample_dirs[1], log=lambda *_: None)


@pytest.fixture(scope="session")
def cleaned_clean(spark, sample_dirs):
    from pipeline import clean
    return clean.clean_all(spark, sample_dirs[0], log=lambda *_: None)
