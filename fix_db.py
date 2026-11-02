import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

try:
    db = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE')
    )
    cursor = db.cursor()
    
    columns = [
        "appointment_id INT DEFAULT NULL",
        "report_id INT DEFAULT NULL",
        "payment_method VARCHAR(50) DEFAULT 'Razorpay'",
        "razorpay_order_id VARCHAR(255) DEFAULT NULL",
        "razorpay_payment_id VARCHAR(255) DEFAULT NULL",
        "razorpay_signature VARCHAR(255) DEFAULT NULL",
        "transaction_id VARCHAR(255) DEFAULT NULL",
        "payment_date TIMESTAMP NULL"
    ]
    
    for col in columns:
        try:
            cursor.execute(f"ALTER TABLE payments ADD COLUMN {col}")
            print(f"Added column {col}")
        except mysql.connector.errors.ProgrammingError as e:
            if e.errno == 1060:
                print(f"Column already exists for {col}")
            else:
                print(f"Error adding {col}: {e}")
                
    db.commit()
    print("Database alterations complete.")
except Exception as e:
    print(f"Connection error: {e}")
