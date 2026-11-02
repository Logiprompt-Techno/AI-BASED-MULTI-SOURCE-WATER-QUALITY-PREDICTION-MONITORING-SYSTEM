from app import app, get_db_connection

def migrate_db():
    with app.app_context():
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        # Check if columns already exist
        cursor.execute("DESCRIBE appointments")
        cols = [row['Field'] for row in cursor.fetchall()]
        
        if 'latitude' not in cols:
            cursor.execute("ALTER TABLE appointments ADD COLUMN latitude DOUBLE DEFAULT NULL")
            print("Added latitude column to appointments table.")
        else:
            print("latitude column already exists.")

        if 'longitude' not in cols:
            cursor.execute("ALTER TABLE appointments ADD COLUMN longitude DOUBLE DEFAULT NULL")
            print("Added longitude column to appointments table.")
        else:
            print("longitude column already exists.")
            
        db.commit()

if __name__ == "__main__":
    migrate_db()
