import sqlite3

con = sqlite3.connect("flask_app/database/resume.db")
con.execute("DELETE FROM skills WHERE skill_id = 1")
con.commit()
print("deleted")