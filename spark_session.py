import os
import sys


def _find_java():
    """If Java isn't on PATH / JAVA_HOME (e.g. a terminal opened before the
    install), look in the usual Windows install folders."""
    import glob
    import shutil
    if os.environ.get("JAVA_HOME") or shutil.which("java"):
        return
    for pattern in (r"C:\Program Files\Eclipse Adoptium\jdk-17*", r"C:\Program Files\Java\jdk-17*",
                    r"C:\Program Files\Microsoft\jdk-17*"):
        hits = sorted(glob.glob(pattern))
        if hits:
            os.environ["JAVA_HOME"] = hits[-1]
            return


def get_spark(app_name="AirlineDigitalTwin", driver_memory="3g"):
    _find_java()
    # Make Spark workers use the same Python as the driver (avoids the
    # common "Python worker failed to connect" error on Windows).
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.session.timeZone", "UTC")
        # Dirty data: failed casts/parses should become NULL, not crash the job.
        .config("spark.sql.ansi.enabled", "false")
        .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.maxPlanStringLength", "100000")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark
