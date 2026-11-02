import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

db = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE")
)

cursor = db.cursor()
cursor.execute("SHOW TABLES")
tables = cursor.fetchall()
print("TABLES:")
for t in tables:
    print(t[0]) # type: ignore
    cursor.execute(f"DESCRIBE {t[0]}") # type: ignore
    desc = cursor.fetchall()
    for col in desc:
        print(f"  {col[0]} - {col[1]} (Key: {col[3]})") # type: ignore
    print("-" * 20)
