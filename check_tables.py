import sqlite3
conn = sqlite3.connect('data/supply_chain.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ci_%' ORDER BY name")
tables = cursor.fetchall()
if tables:
    for t in tables: print('  OK', t[0])
else:
    print('  NO CI TABLES FOUND - run setup scripts first')
conn.close()
