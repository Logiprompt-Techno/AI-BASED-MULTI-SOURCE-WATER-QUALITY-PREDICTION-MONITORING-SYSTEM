import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

try:
    db = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )
    cursor = db.cursor(dictionary=True)
    cursor.execute("DESCRIBE users;")
    for row in cursor.fetchall():
        print(row)
except Exception as e:
    print(e)
