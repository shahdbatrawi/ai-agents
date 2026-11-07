"""Print real semantic scores using separate development test data."""

import importlib.util
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


database_module = load_module(
    "calibration_database",
    ROOT / "flask_app" / "utils" / "database.py",
)

search_module = load_module(
    "calibration_search",
    ROOT / "flask_app" / "utils" / "semantic_search.py",
)

db = database_module.database()

# This database is separate from the application's resume.db.
# Keep it between runs so successful embeddings can be reused.
db.db_path = str(ROOT / "tests" / "calibration.db")

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)

    shutil.copytree(
        ROOT / "flask_app" / "database" / "create_tables",
        folder / "create_tables",
    )

    initial_data = folder / "initial_data"
    initial_data.mkdir()

    for table in ("institutions", "positions", "experiences", "skills"):
        shutil.copyfile(
            ROOT / "tests" / "sample_data" / f"{table}.csv",
            initial_data / f"{table}.csv",
        )

    shutil.copyfile(
        ROOT / "flask_app" / "database" / "initial_data" / "llm_roles.csv",
        initial_data / "llm_roles.csv",
    )

    database_module.DATABASE_FOLDER = str(folder)
    db.createTables()

# Local development additions, not the official HW2 fixtures.
for name in ("Machine Learning", "Public Speaking"):
    existing = db.query(
        "SELECT skill_id FROM skills WHERE name = ?",
        (name,),
    )

    if not existing:
        db.query(
            "INSERT INTO skills (experience_id, name, skill_level) "
            "VALUES (NULL, ?, 5)",
            (name,),
        )

search = search_module.SemanticSearch(db)

queries = [
    ("MSU experience", ["institutions"]),
    ("Harvard experience", ["institutions"]),
    ("AI skills", ["skills"]),
]

for question, tables in queries:
    print(f"\nQUERY: {question}", flush=True)
    print(f"TABLES: {tables}", flush=True)

    # Show all scores for calibration; this is not a final cutoff.
    matches = search.search(
        question,
        tables,
        min_score=-1.0,
        top_k=20,
    )

    for match in matches:
        print(
            f"{match['score']:.6f} | "
            f"{match['table']} #{match['record_id']} | "
            f"{match['text']}",
            flush=True,
        )

print("\nCalibration finished. App resume.db was not changed.")