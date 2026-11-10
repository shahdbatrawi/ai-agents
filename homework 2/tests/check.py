import sqlite3

con = sqlite3.connect("flask_app/database/resume.db")

print("--- skills named javascript (any case) ---")
for row in con.execute("SELECT * FROM skills WHERE LOWER(name) = 'javascript'"):
    print(row)

print("--- experiences ---")
for row in con.execute("SELECT * FROM experiences"):
    print(row)