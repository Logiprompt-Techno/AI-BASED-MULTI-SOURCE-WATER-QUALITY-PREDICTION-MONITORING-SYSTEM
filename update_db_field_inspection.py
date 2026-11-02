import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=True)

def update_database():
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DATABASE', 'aquaguard')
        )
        cursor = conn.cursor()

        # 1. Alter field_inspections table to add new columns
        print("Adding new columns to field_inspections table...")
        new_columns = [
            ("sample_id", "VARCHAR(100)"),
            ("sample_collection_time", "TIME"),
            ("sample_type", "VARCHAR(100)"),
            ("sample_count", "INT"),
            ("container_type", "VARCHAR(100)"),
            ("preservation_method", "VARCHAR(255)"),
            ("sample_sent_to_lab", "VARCHAR(10)"),
            ("laboratory_name", "VARCHAR(255)"),
            ("laboratory_ref", "VARCHAR(100)"),
            ("inspection_summary", "TEXT"),
            ("recommended_action", "TEXT")
        ]

        # Check existing columns to avoid duplicate column errors
        cursor.execute("DESCRIBE field_inspections")
        existing_columns = [row[0] for row in cursor.fetchall()] # type: ignore

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                cursor.execute(f"ALTER TABLE field_inspections ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name}")
            else:
                print(f"Column {col_name} already exists.")

        # 2. Create field_inspection_photos table
        print("Creating field_inspection_photos table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_inspection_photos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                inspection_id INT NOT NULL,
                photo_type VARCHAR(100),
                file_path VARCHAR(255),
                description TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inspection_id) REFERENCES field_inspections(id) ON DELETE CASCADE
            )
        """)

        # 3. Create field_inspection_techniques table
        print("Creating field_inspection_techniques table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_inspection_techniques (
                id INT AUTO_INCREMENT PRIMARY KEY,
                inspection_id INT NOT NULL,
                technique VARCHAR(100),
                notes TEXT,
                equipment_name VARCHAR(150),
                equipment_model VARCHAR(150),
                instrument_id VARCHAR(100),
                calibration_status VARCHAR(100),
                calibration_date DATE,
                measurement_unit VARCHAR(50),
                remarks TEXT,
                FOREIGN KEY (inspection_id) REFERENCES field_inspections(id) ON DELETE CASCADE
            )
        """)

        # 4. Create field_inspection_measurements table
        print("Creating field_inspection_measurements table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_inspection_measurements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                inspection_id INT NOT NULL,
                parameter VARCHAR(100),
                value FLOAT,
                unit VARCHAR(50),
                technique VARCHAR(100),
                instrument VARCHAR(150),
                measurement_time TIME,
                remarks TEXT,
                FOREIGN KEY (inspection_id) REFERENCES field_inspections(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        print("Database update successful!")

    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    update_database()
