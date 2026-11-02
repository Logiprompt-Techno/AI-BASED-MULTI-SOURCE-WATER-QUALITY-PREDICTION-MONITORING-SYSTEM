import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=True)

db = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
)

cursor = db.cursor()
try:
    cursor.execute("ALTER TABLE predictions ADD COLUMN custom_parameters TEXT DEFAULT NULL")
    db.commit()
    print("Added custom_parameters column to predictions table.")
except mysql.connector.Error as err:
    if err.errno == 1060: # Duplicate column name
        print("Column custom_parameters already exists.")
    else:
        print(f"Error: {err}")
finally:
    cursor.close()
    db.close()
