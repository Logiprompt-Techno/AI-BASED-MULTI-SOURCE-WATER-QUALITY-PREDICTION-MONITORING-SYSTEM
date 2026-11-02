import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    db = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', 'aquaguard')
    )
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_NAME='appointments'")
    for c in cursor.fetchall():
        print(c)

except Exception as e:
    print(f"Error connecting to DB: {e}")
