import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=True)

def migrate_database():
    db = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', 'aquaguard')
    )
    cursor = db.cursor(dictionary=True)
    
    columns_to_add = [
        ("assignment_status", "VARCHAR(50) DEFAULT 'Pending Inspector Approval'"),
        ("assigned_inspector_id", "INT DEFAULT NULL"),
        ("inspector_approval_time", "DATETIME DEFAULT NULL"),
        ("inspector_rejection_time", "DATETIME DEFAULT NULL"),
        ("rejection_reason", "TEXT DEFAULT NULL"),
        ("inspection_started_time", "DATETIME DEFAULT NULL"),
        ("inspection_completed_time", "DATETIME DEFAULT NULL"),
        ("rejected_inspector_id", "INT DEFAULT NULL")
    ]
    
    cursor.execute("DESCRIBE appointments")
    existing_columns = [row['Field'] for row in cursor.fetchall()]
    
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            print(f"Adding column '{col_name}' to appointments table...")
            cursor.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_type}")
            db.commit()
        else:
            print(f"Column '{col_name}' already exists in appointments table.")
            
    cursor.close()
    db.close()
    print("Database migration completed successfully!")

if __name__ == '__main__':
    migrate_database()
