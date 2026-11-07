import csv
import importlib.util
import shutil
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
source = root / "flask_app" / "utils" / "database.py"

spec = importlib.util.spec_from_file_location("startup_database", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)

    for name in ("create_tables", "initial_data"):
        shutil.copytree(
            root / "flask_app" / "database" / name,
            folder / name,
        )

    module.DATABASE_FOLDER = str(folder)
    module.DB_PATH = str(folder / "test.db")

    db = module.database()
    db.createTables()

    skills = db.query("SELECT * FROM skills ORDER BY skill_id")
    assert skills, "FAIL: No initial skills loaded."

    skill_id = skills[0]["skill_id"]
    db.query("DELETE FROM skills WHERE skill_id = ?", (skill_id,))

    roles_file = folder / "initial_data" / "llm_roles.csv"
    with roles_file.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        roles = list(reader)

    assert roles, "FAIL: No role configuration loaded."
    roles[0]["specific_instructions"] = "Temporary startup test."

    with roles_file.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(roles)

    restarted = module.database()
    restarted.createTables()

    assert not restarted.query(
        "SELECT * FROM skills WHERE skill_id = ?", (skill_id,)
    ), "FAIL: Deleted skill returned."

    assert len(restarted.query("SELECT * FROM skills")) == len(skills) - 1
    print("PASS: Deleted skill stays deleted after restart.")

    role = restarted.query(
        "SELECT specific_instructions FROM llm_roles WHERE role = ?",
        (roles[0]["role"],),
    )
    assert role[0]["specific_instructions"] == "Temporary startup test."
    print("PASS: Prompt changes load after restart.")

print("Temporary test finished; app database was not changed.")