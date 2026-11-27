import sqlite3

conn = sqlite3.connect("data/detectiq.db")
conn.close()

print("Database created successfully!")