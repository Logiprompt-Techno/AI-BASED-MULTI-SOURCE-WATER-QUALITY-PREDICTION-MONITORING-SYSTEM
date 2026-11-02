import os
import json
import pickle
import numpy as np
from datetime import datetime, timedelta, date, time
from decimal import Decimal

def make_json_serializable(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    elif isinstance(obj, (datetime, date, time, timedelta)):
        return str(obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, bytes):
        return obj.decode('utf-8', errors='ignore')
    return obj

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import csv
import io
import traceback
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from groq import Groq
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, classification_report
import re
import hashlib
import secrets
from flask_wtf.csrf import CSRFProtect
from email_validator import validate_email, EmailNotValidError
from flask_mail import Mail, Message
load_dotenv(override=True)

from typing import Any
imputer: Any = None
model: Any = None

# Debug print to verify variables are loaded
print("Loaded DB:", os.getenv("MYSQL_DATABASE"))

def calculate_wqi(do, ph, bod, nitrate, cond):
    score = (abs(ph-7)*10) + (bod*5) + (nitrate*2) + (cond/100)
    if do < 5: score += 20
    if score < 26: cat = "Excellent"
    elif score < 51: cat = "Good"
    elif score < 76: cat = "Poor"
    elif score < 101: cat = "Very Poor"
    else: cat = "Unsuitable"
    return round(score, 1), cat

def get_model_metrics():
    if imputer is None or model is None:
        return {"accuracy": 0, "precision": 0, "recall": 0, "f1": 0, "conf_matrix": [[0,0],[0,0]], "class_report": {}, "total_samples": 0, "test_samples": 0, "n_features": 0}
    
    np.random.seed(99)
    n_samples = 500
    X = pd.DataFrame({
        'Temperature': np.random.uniform(15, 35, n_samples),
        'DO': np.random.uniform(0, 10, n_samples),
        'pH': np.random.uniform(4, 10, n_samples),
        'BOD': np.random.uniform(0, 20, n_samples),
        'Faecal_Streptococci': np.random.uniform(0, 500, n_samples),
        'Nitrate': np.random.uniform(0, 50, n_samples),
        'Faecal_Coliform': np.random.uniform(0, 1000, n_samples),
        'Total_Coliform': np.random.uniform(0, 2000, n_samples),
        'Conductivity': np.random.uniform(100, 1000, n_samples)
    })
    
    safe_condition = (X['DO'] > 4) & (X['pH'] >= 6.0) & (X['pH'] <= 9.0) & (X['BOD'] < 10)
    y_true = np.where(safe_condition, 1, 0)
    
    X_imputed = imputer.transform(X)
    y_pred = model.predict(X_imputed)
    
    metrics = {
        "accuracy": round(accuracy_score(y_true, y_pred) * 100, 2),
        "precision": round(precision_score(y_true, y_pred, zero_division=0) * 100, 2), # type: ignore
        "recall": round(recall_score(y_true, y_pred, zero_division=0) * 100, 2), # type: ignore
        "f1": round(f1_score(y_true, y_pred, zero_division=0) * 100, 2), # type: ignore
        "conf_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "class_report": classification_report(y_true, y_pred, output_dict=True, zero_division=0), # type: ignore
        "total_samples": 1000, 
        "test_samples": 500,
        "n_features": 9
    }
    return metrics

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
csrf = CSRFProtect(app)

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_no_cache_headers(response):
    if request.endpoint == 'static':
        return response
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.template_filter('fromjson')
def fromjson_filter(s):
    try:
        import json
        return json.loads(s) if s else []
    except:
        return []

@app.template_filter('safe_strftime')
def safe_strftime_filter(val, fmt='%Y-%m-%d'):
    if not val:
        return ''
    if isinstance(val, (datetime, date)):
        return val.strftime(fmt)
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return ''
        clean_str = val_str.replace('T', ' ')
        for dt_fmt in (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%d-%m-%Y %H:%M:%S',
            '%d-%m-%Y %H:%M',
            '%d-%m-%Y',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
            '%B %d, %Y at %H:%M',
            '%B %d, %Y',
            '%H:%M:%S',
            '%H:%M'
        ):
            try:
                dt_obj = datetime.strptime(clean_str, dt_fmt)
                return dt_obj.strftime(fmt)
            except (ValueError, TypeError):
                continue
        return val_str
    return str(val)


# Flask-Mail config
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = str(os.getenv('MAIL_USE_TLS', 'True')).lower() in ['true', 'on', '1']
app.config['MAIL_USE_SSL'] = str(os.getenv('MAIL_USE_SSL', 'False')).lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or os.getenv('MAIL_USERNAME')
mail = Mail(app)



def is_valid_password(password):
    if not password or len(password) < 6:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def is_valid_name(name):
    if not name:
        return False
    return bool(re.match(r"^[A-Za-z\s]+$", name))

def is_valid_phone(phone):
    if not phone:
        return False
    return bool(re.match(r"^\d{10}$", phone))

def is_valid_email(email):
    if not email:
        return False
    if not email.lower().endswith("@gmail.com"):
        return False
    try:
        validate_email(email)
        return True
    except:
        return False


@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profile')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 # 2MB limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

from flask import g
from werkzeug.local import LocalProxy
import mysql.connector.pooling

# Connection Pool Initialization
try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="aquaguard_pool",
        pool_size=10,
        pool_reset_session=True,
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )
    
    # Initialize DB schema once on startup
    init_db = db_pool.get_connection()
    init_cursor = init_db.cursor(dictionary=True)
    
    # Create contact_messages table if not exists
    init_cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Alter contact_messages to add new messaging system columns if they don't exist
    try:
        init_cursor.execute("ALTER TABLE contact_messages ADD COLUMN user_id INT DEFAULT NULL")
        init_cursor.execute("ALTER TABLE contact_messages ADD COLUMN status VARCHAR(20) DEFAULT 'Pending'")
        init_cursor.execute("ALTER TABLE contact_messages ADD COLUMN reply_message TEXT DEFAULT NULL")
        init_cursor.execute("ALTER TABLE contact_messages ADD COLUMN reply_date TIMESTAMP NULL")
        init_db.commit()
    except mysql.connector.Error:
        pass # Columns probably already exist
    
    # Alter users table to add new profile columns if they don't exist
    try:
        init_cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user'")
        init_cursor.execute("ALTER TABLE users ADD COLUMN mobile VARCHAR(20) DEFAULT NULL")
        init_cursor.execute("ALTER TABLE users ADD COLUMN phone_number VARCHAR(20) UNIQUE DEFAULT NULL")
        init_cursor.execute("ALTER TABLE users ADD COLUMN profile_image VARCHAR(255) DEFAULT 'default.png'")
        init_cursor.execute("ALTER TABLE users ADD COLUMN status VARCHAR(50) DEFAULT 'active'")
        init_cursor.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP NULL")
        init_db.commit()
    except mysql.connector.Error:
        pass # Columns probably already exist
        
    try:
        init_cursor.execute("ALTER TABLE predictions ADD COLUMN prediction_source VARCHAR(50) DEFAULT 'Manual Entry'")
        init_db.commit()
    except mysql.connector.Error:
        pass # Column probably already exists

    # Create feedbacks table and add workflow columns to appointments dynamically
    try:
        init_cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                feedback_id INT AUTO_INCREMENT PRIMARY KEY,
                appointment_id INT NOT NULL,
                user_id INT NOT NULL,
                rating INT NOT NULL,
                categories VARCHAR(500),
                comments TEXT,
                recommendation VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        init_db.commit()
    except mysql.connector.Error:
        pass

    for col_name, col_type in [
        ("assigned_at", "TIMESTAMP NULL DEFAULT NULL"),
        ("accepted_at", "TIMESTAMP NULL DEFAULT NULL"),
        ("completed_at", "TIMESTAMP NULL DEFAULT NULL"),
        ("rejected_inspector_id", "INT DEFAULT NULL"),
        ("rejection_reason", "TEXT DEFAULT NULL"),
        ("rejected_at", "TIMESTAMP NULL DEFAULT NULL"),
        ("inspection_type", "VARCHAR(100) DEFAULT 'Online Inspection'"),
        ("online_status", "VARCHAR(50) DEFAULT 'Pending'"),
        ("field_status", "VARCHAR(50) DEFAULT 'Pending'"),
        ("online_date", "VARCHAR(50) DEFAULT NULL"),
        ("online_time", "VARCHAR(50) DEFAULT NULL"),
        ("field_date", "VARCHAR(50) DEFAULT NULL"),
        ("field_time", "VARCHAR(50) DEFAULT NULL")
    ]:
        try:
            init_cursor.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_type};")
            init_db.commit()
        except mysql.connector.Error:
            pass

    try:
        # Prepopulate old records with compatible defaults
        init_cursor.execute("UPDATE appointments SET inspection_type = 'Online Inspection' WHERE inspection_type IS NULL;")
        init_cursor.execute("UPDATE appointments SET online_status = 'Completed' WHERE status = 'Completed' AND online_status = 'Pending';")
        init_cursor.execute("UPDATE appointments SET field_status = 'N/A' WHERE status = 'Completed' AND field_status = 'Pending';")
        init_cursor.execute("UPDATE appointments SET field_status = 'Completed' WHERE appointment_id IN (SELECT appointment_id FROM field_inspections WHERE appointment_id IS NOT NULL);")
        init_db.commit()
    except mysql.connector.Error:
        pass

    try:
        init_cursor.execute("DROP TABLE IF EXISTS admins")
        init_db.commit()
    except mysql.connector.Error:
        pass

    # Create password_resets table if not exists
    try:
        init_cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(150) NOT NULL,
                token VARCHAR(255) NOT NULL,
                user_type VARCHAR(20) NOT NULL DEFAULT 'user',
                expires_at DATETIME NOT NULL,
                used TINYINT(1) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_token (token),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        init_db.commit()
    except mysql.connector.Error:
        pass

    # Ensure default admin exists
    init_cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not init_cursor.fetchone():
        admin_email = os.getenv("ADMIN_EMAIL", "admin@aquaguard.com")
        admin_pass = generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123"))
        init_cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            ("System Administrator", admin_email, admin_pass, "admin")
        )

    init_db.commit()
    init_cursor.close()
    init_db.close()
    
    print("MySQL Connected and Initialized Successfully")
except mysql.connector.Error as err:
    print("MySQL Connection Failed:", err)
    db_pool = None

def get_db_connection():
    if 'db' not in g:
        try:
            if db_pool:
                g.db = db_pool.get_connection()
            else:
                # Fallback if pool failed during startup
                g.db = mysql.connector.connect(
                    host=os.getenv("MYSQL_HOST"),
                    user=os.getenv("MYSQL_USER"),
                    password=os.getenv("MYSQL_PASSWORD"),
                    database=os.getenv("MYSQL_DATABASE"),
                )
        except mysql.connector.Error as e:
            print(f"Database connection error: {e}")
            raise
    return g.db

def get_db_cursor():
    if 'cursor' not in g:
        g.cursor = get_db_connection().cursor(dictionary=True)
    return g.cursor

@app.teardown_appcontext
def close_db_connection(exception=None):
    db_cursor = g.pop('cursor', None)
    if db_cursor is not None:
        try:
            db_cursor.close()
        except Exception:
            pass
            
    db_conn = g.pop('db', None)
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass

# Safely inject request-scoped connections into existing code logic
db = LocalProxy(get_db_connection)
cursor = LocalProxy(get_db_cursor)

# Load models
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
imputer_path = os.path.join(BASE_DIR, "wqi_imputer.pkl")
model_path = os.path.join(BASE_DIR, "wqi_model.pkl")

try:
    with open(imputer_path, "rb") as f:
        imputer = pickle.load(f)
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    print("Models loaded successfully.")
except Exception as e:
    print(f"Error loading models: {e}")
    imputer, model = None, None


@app.route("/")
def index():
    if session.get("logged_out"):
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if db is None or not db.is_connected():
            flash("Database connection error. Please try again later.", "danger")
            return render_template("register.html")

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "user")
        district = request.form.get("district", "Not Specified").strip()
        designation = request.form.get("designation", "Inspector").strip()

        if not name or not email or not phone or not location or not password or not confirm_password:
            flash("Please fill in all required fields before submitting.", "danger")
            return render_template("register.html")
            
        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return render_template("register.html")
            
        if not is_valid_name(name):
            flash("Name must contain letters and spaces only.", "danger")
            return render_template("register.html")
            
        if not is_valid_email(email):
            flash("Please enter a valid Gmail address ending with @gmail.com.", "danger")
            return render_template("register.html")
            
        if not is_valid_phone(phone):
            flash("Phone number must contain exactly 10 digits.", "danger")
            return render_template("register.html")
            
        if not is_valid_password(password):
            flash("Password must contain at least one letter and one number.", "danger")
            return render_template("register.html")

        try:
            if role == "inspector":
                if not district: district = "Not Specified"
                if not designation: designation = "Inspector"
                cursor.execute("SELECT inspector_id FROM inspectors WHERE email = %s OR phone = %s", (email, phone))
                if cursor.fetchone():
                    flash("Email or Phone Number already registered", "danger")
                    return render_template("register.html")
                hashed_password = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO inspectors (full_name, email, phone, password, district, designation) VALUES (%s, %s, %s, %s, %s, %s)",
                    (name, email, phone, hashed_password, district, designation),
                )
            else:
                cursor.execute("SELECT id FROM users WHERE email = %s OR phone_number = %s", (email, phone))
                if cursor.fetchone():
                    flash("Email or Phone Number already registered", "danger")
                    return render_template("register.html")
    
                hashed_password = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (name, email, phone_number, password, location) VALUES (%s, %s, %s, %s, %s)",
                    (name, email, phone, hashed_password, location),
                )
            db.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as e:
            flash("A database error occurred. Could not register.", "danger")
            print(f"DB Error: {e}")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if db is None or not db.is_connected():
            flash("Database connection error. Please try again later.", "danger")
            return render_template("login.html")

        email_or_phone = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        if not email_or_phone or not password:
            flash("Email/Phone and password are required.", "danger")
            return render_template("login.html")

        try:
            cursor.execute("SELECT * FROM users WHERE email = %s OR phone_number = %s", (email_or_phone, email_or_phone))
            user = cursor.fetchone()

            if user and check_password_hash(user["password"], password):
                if user.get("status") != "active":
                    flash("Your account is currently inactive. Please contact support.", "danger")
                    return render_template("login.html")
                    
                # Update last login
                cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user["id"],))
                db.commit()
                
                session.clear()
                session["user_id"] = user["id"]
                session["name"] = user["name"]
                session["email"] = user["email"]
                session["role"] = user.get("role", "user")
                session["mobile"] = user.get("mobile") or user.get("phone_number") or ""
                session["phone"] = user.get("phone_number") or user.get("mobile") or ""
                
                flash("Login successful!", "success")
                if session["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("dashboard"))
                
            # If not found in users, check inspectors table
            cursor.execute("SELECT * FROM inspectors WHERE email = %s OR phone = %s", (email_or_phone, email_or_phone))
            inspector = cursor.fetchone()
            
            if inspector and check_password_hash(inspector["password"], password):
                if inspector.get("status", "Active") != "Active":
                    flash("Your account is currently inactive. Please contact support.", "danger")
                    return render_template("login.html")
                    
                session.clear()
                session["user_id"] = inspector["inspector_id"]
                session["name"] = inspector["full_name"]
                session["email"] = inspector["email"]
                session["role"] = "inspector"
                session["designation"] = inspector["designation"]
                
                flash("Login successful!", "success")
                return redirect(url_for("inspector_dashboard"))
                
            flash("Invalid Email or Password", "danger")
        except mysql.connector.Error as e:
            flash("A database error occurred during login.", "danger")
            print(f"DB Error: {e}")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    session["logged_out"] = True
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        if db is None or not db.is_connected():
            flash("Database connection error. Please try again later.", "danger")
            return render_template("forgot_password.html")

        raw_email = request.form.get("email", "")
        email = raw_email.strip()
        if not email:
            flash("Please enter your registered email address.", "danger")
            return render_template("forgot_password.html")

        if not is_valid_email(email):
            flash("Please enter a valid Gmail address ending with @gmail.com.", "danger")
            return render_template("forgot_password.html")

        try:
            # Case-insensitive and trimmed lookup in users table
            cursor.execute("SELECT id, name, email FROM users WHERE LOWER(TRIM(email)) = LOWER(%s)", (email,))
            user = cursor.fetchone()
            user_type = "user"

            if not user:
                # Check inspectors table if not in users
                cursor.execute("SELECT inspector_id as id, full_name as name, email FROM inspectors WHERE LOWER(TRIM(email)) = LOWER(%s)", (email,))
                user = cursor.fetchone()
                user_type = "inspector"

            if not user:
                flash("This email is not registered. Please create a new account.", "warning")
                return redirect(url_for("register", email=email))

            # Store verified email securely in session for password reset
            session["reset_verified_email"] = user["email"]
            session["reset_user_type"] = user_type

            return redirect(url_for("reset_password"))

        except mysql.connector.Error as e:
            flash("A database error occurred. Please try again.", "danger")
            print(f"DB Error: {e}")

    return render_template("forgot_password.html")


@app.route("/reset_password", methods=["GET", "POST"])
@app.route("/create_new_password", methods=["GET", "POST"])
def reset_password():
    verified_email = session.get("reset_verified_email")
    user_type = session.get("reset_user_type", "user")

    if not verified_email:
        flash("Please enter your registered email address to start the password reset process.", "warning")
        return redirect(url_for("forgot_password"))

    if db is None or not db.is_connected():
        flash("Database connection error. Please try again later.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            flash("Please fill in both password fields.", "danger")
            return render_template("reset_password.html")

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return render_template("reset_password.html")

        if not is_valid_password(password):
            flash("Password must contain at least one letter and one number.", "danger")
            return render_template("reset_password.html")

        try:
            hashed_password = generate_password_hash(password)

            if user_type == "inspector":
                cursor.execute("UPDATE inspectors SET password = %s WHERE LOWER(TRIM(email)) = LOWER(%s)", (hashed_password, verified_email))
            else:
                cursor.execute("UPDATE users SET password = %s WHERE LOWER(TRIM(email)) = LOWER(%s)", (hashed_password, verified_email))

            db.commit()

            # Clear reset session state after successful password update
            session.pop("reset_verified_email", None)
            session.pop("reset_user_type", None)

            flash("Password reset successfully. You can now log in with your new password.", "success")
            return redirect(url_for("login"))

        except mysql.connector.Error as e:
            flash("A database error occurred. Please try again.", "danger")
            print(f"DB Error: {e}")
            return render_template("reset_password.html")

    return render_template("reset_password.html")


@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password_with_token(token):
    return redirect(url_for("forgot_password"))


@app.route("/predict", methods=["GET", "POST"])
@login_required
def predict():
    if session.get("role") != "user":
        flash("Please login to use the prediction feature", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        source = request.form.get("source")
        prediction_source = request.form.get("prediction_source", "Manual Entry")
        try:
            # Extract features
            temp = float(request.form.get("temperature", 0))
            do = float(request.form.get("do", 0))
            ph = float(request.form.get("ph", 0))
            bod = float(request.form.get("bod", 0))
            f_strep = float(request.form.get("f_strep", 0))
            nitrate = float(request.form.get("nitrate", 0))
            f_coli = float(request.form.get("f_coli", 0))
            t_coli = float(request.form.get("t_coli", 0))
            cond = float(request.form.get("conductivity", 0))
            
            # Extract custom parameters
            custom_names = request.form.getlist("custom_name[]")
            custom_values = request.form.getlist("custom_value[]")
            custom_units = request.form.getlist("custom_unit[]")
            
            custom_params = []
            for n, v, u in zip(custom_names, custom_values, custom_units):
                if n.strip() and v.strip():
                    custom_params.append({
                        "name": n.strip(),
                        "value": v.strip(),
                        "unit": u.strip()
                    })
            custom_params_json = json.dumps(custom_params) if custom_params else None
            
            # Validation
            if not (0 <= ph <= 14):
                flash("pH must be between 0 and 14.", "danger")
                return render_template("predict.html", source=source)
            if any(val < 0 for val in [do, bod, f_strep, nitrate, f_coli, t_coli, cond]):
                flash("Water quality parameters cannot be negative.", "danger")
                return render_template("predict.html", source=source)
            if temp < -50 or temp > 100:
                flash("Temperature is out of valid scientific range (-50 to 100).", "danger")
                return render_template("predict.html", source=source)

            features = np.array(
                [[temp, do, ph, bod, f_strep, nitrate, f_coli, t_coli, cond]]
            )

            if imputer and model:
                features_imputed = imputer.transform(features)
                prediction = model.predict(features_imputed)[0]
            else:
                flash("Models not loaded", "danger")
                return render_template("predict.html", source=source)

            status = "SAFE" if prediction == 1 else "UNSAFE"

            # Simple heuristic for pollution level
            if prediction == 1:
                if bod < 5 and do > 6:
                    pollution = "Low"
                else:
                    pollution = "Medium"
            else:
                pollution = "High"

            # Recommendations
            if status == "SAFE":
                rec = "Drinking, Irrigation"
            else:
                rec = "Not safe"

            prediction_data = {
                "user_id": session["user_id"],
                "source": source,
                "prediction_source": prediction_source,
                "parameters": {
                    "temperature": temp,
                    "do": do,
                    "ph": ph,
                    "bod": bod,
                    "f_strep": f_strep,
                    "nitrate": nitrate,
                    "f_coli": f_coli,
                    "t_coli": t_coli,
                    "conductivity": cond
            },
                "status": status,
                "pollution_level": pollution,
                "recommendation": rec,
                "timestamp": datetime.now(),
                "custom_parameters": custom_params

            }

            if db and db.is_connected():
                try:
                    sql = """
                    INSERT INTO predictions 
                    (user_id, water_source, temperature, dissolved_oxygen, ph, bod, 
                     nitrate, faecal_coliform, total_coliform, conductivity, 
                     prediction, pollution_level, recommendation, prediction_source, custom_parameters)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    val = (
                        session["user_id"],
                        source,
                        temp,
                        do,
                        ph,
                        bod,
                        nitrate,
                        f_coli,
                        t_coli,
                        cond,
                        status,
                        pollution,
                        rec,
                        prediction_source,
                        custom_params_json
                    )
                    cursor.execute(sql, val)
                    prediction_id = cursor.lastrowid
                    prediction_data["id"] = prediction_id
                    db.commit()
                except mysql.connector.Error as e:
                    flash(
                        "Prediction made, but could not save to history due to database error.",
                        "warning",
                    )
                    print(f"DB Error: {e}")
            else:
                flash(
                    "Prediction made, but database connection error prevented saving history.",
                    "warning",
                )

            return render_template("result.html", data=prediction_data)

        except ValueError:
            flash("Invalid input data. All parameters must be numeric.", "danger")
            return render_template("predict.html", source=request.form.get("source", "Tap Water"))
        except Exception as e:
            flash(f"Error making prediction: {str(e)}", "danger")
            return render_template("predict.html", source=request.form.get("source", "Tap Water"))

    return render_template(
        "predict.html", source=request.args.get("source", "Tap Water")
    )


import PyPDF2

@app.route("/extract_pdf", methods=["POST"])
@csrf.exempt
@login_required
def extract_pdf():
    if session.get("role") not in ["user", "inspector"]:
        return jsonify({"error": "Unauthorized"}), 401
    
    if 'pdf_file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['pdf_file']
    filename = file.filename
    if not filename:
        return jsonify({"error": "Empty file"}), 400
        
    if not filename.lower().endswith('.pdf'):
        return jsonify({"error": "Only PDF files are allowed"}), 400
        
    try:
        reader = PyPDF2.PdfReader(file.stream) # type: ignore
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
            
        if not text.strip():
            return jsonify({"error": "Could not extract readable text from PDF"}), 400
            
        # Regex patterns to find parameters
        params = {
            "temperature": r"(?i)temperature\s*\(?°c\)?\s*[:\-=]?\s*([\d.]+)",
            "do": r"(?i)(?:dissolved oxygen|do)\s*\(?mg/l\)?\s*[:\-=]?\s*([\d.]+)",
            "ph": r"(?i)ph(?: value| level)?\s*[:\-=]?\s*([\d.]+)",
            "bod": r"(?i)bod\s*\(?mg/l\)?\s*[:\-=]?\s*([\d.]+)",
            "faecal_streptococci": r"(?i)fa?ecal streptococci\s*\(?mpn/100ml\)?\s*[:\-=]?\s*([\d.]+)",
            "nitrate": r"(?i)nitrate\s*\(?mg/l\)?\s*[:\-=]?\s*([\d.]+)",
            "faecal_coliform": r"(?i)fa?ecal coliform\s*\(?mpn/100ml\)?\s*[:\-=]?\s*([\d.]+)",
            "total_coliform": r"(?i)total coliform\s*\(?mpn/100ml\)?\s*[:\-=]?\s*([\d.]+)",
            "conductivity": r"(?i)conductivity\s*\(?(?:µs/cm|us/cm)\)?\s*[:\-=]?\s*([\d.]+)",
        }
        
        extracted = {}
        for key, pattern in params.items():
            match = re.search(pattern, text)
            if match:
                try:
                    extracted[key] = float(match.group(1))
                except ValueError:
                    extracted[key] = None
            else:
                extracted[key] = None
                
        return jsonify({"success": True, "data": extracted})
        
    except Exception as e:
        return jsonify({"error": f"Error parsing PDF: {str(e)}"}), 500


@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") != "user":
        return redirect(url_for("login"))

    if db is None or not db.is_connected():
        flash("Database connection error. Dashboard stats are unavailable.", "danger")
        stats = {"total": 0, "safe": 0, "unsafe": 0, "sources": {}, "history": []}
        return render_template("dashboard.html", stats=stats)

    try:
        user_id = session["user_id"]
        cursor.execute(
            "SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        predictions = cursor.fetchall()

        total = len(predictions)
        safe = sum(1 for p in predictions if p["prediction"] == "SAFE")
        unsafe = total - safe

        # Source analysis
        sources = {}
        history = []
        wqi_sum = 0
        monthly_data = {str(i): 0 for i in range(1, 13)}
        wqi_trend = []
        param_comparison = {'do': 0.0, 'ph': 0.0, 'bod': 0.0, 'nitrate': 0.0}
        
        for p in predictions:
            src = p["water_source"]
            sources[src] = sources.get(src, 0) + 1
            
            wqi_score, wqi_cat = calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])
            wqi_sum += wqi_score
            
            month = p["created_at"].month
            monthly_data[str(month)] += 1
            wqi_trend.append(wqi_score)
            
            param_comparison['do'] += p["dissolved_oxygen"]
            param_comparison['ph'] += p["ph"]
            param_comparison['bod'] += p["bod"]
            param_comparison['nitrate'] += p["nitrate"]

            history.append(
                {
                    "id": p["id"],
                    "source": src,
                    "prediction_source": p.get("prediction_source", "Manual Entry"),
                    "status": p["prediction"],
                    "pollution_level": p["pollution_level"],
                    "wqi": wqi_score,
                    "wqi_category": wqi_cat,
                    "timestamp": p["created_at"]
            }
            )

        avg_wqi = round(wqi_sum / total, 1) if total > 0 else 0
        wqi_trend = wqi_trend[:10][::-1]
        
        if total > 0:
            for k in param_comparison:
                param_comparison[k] = round(param_comparison[k] / total, 1)

        model_metrics = get_model_metrics()

        stats = {
            "total": total,
            "safe": safe,
            "unsafe": unsafe,
            "avg_wqi": avg_wqi,
            "sources": sources,
            "monthly": list(monthly_data.values()),
            "wqi_trend": wqi_trend,
            "param_comparison": param_comparison,
            "history": history[:10],
            "model_accuracy": model_metrics["accuracy"]
        }

        return render_template("dashboard.html", stats=stats)
    except mysql.connector.Error as e:
        flash("A database error occurred loading the dashboard.", "danger")
        print(f"DB Error: {e}")
        stats = {"total": 0, "safe": 0, "unsafe": 0, "sources": {}, "history": []}
        return render_template("dashboard.html", stats=stats)


@app.route("/about")
def about():
    if session.get("logged_out"):
        return redirect(url_for("login"))
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if session.get("logged_out"):
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        subject = request.form.get("subject")
        message = request.form.get("message")
        
        if not (name and email and subject and message):
            flash("Please fill in all required fields before submitting.", "danger")
            return redirect(url_for("contact"))
            
        if not is_valid_name(name):
            flash("Name must contain letters and spaces only.", "danger")
            return redirect(url_for("contact"))
            
        if not is_valid_email(email):
            flash("Please enter a valid Gmail address ending with @gmail.com.", "danger")
            return redirect(url_for("contact"))
            
        if db is None or not db.is_connected():
            flash("Database connection error. Please try again later.", "danger")
            return redirect(url_for("contact"))
            
        try:
            user_id = session.get("user_id")
            cursor.execute(
                "INSERT INTO contact_messages (name, email, subject, message, user_id) VALUES (%s, %s, %s, %s, %s)",
                (name, email, subject, message, user_id)
            )
            db.commit()
            flash("Thank you for your message! We will get back to you soon.", "success")
        except mysql.connector.Error as e:
            flash("An error occurred. Please try again later.", "danger")
            print(f"DB Error: {e}")
            
        return redirect(url_for("contact"))
    return render_template("contact.html")


@app.route("/messages")
@login_required
def user_messages():
    if session.get("role") != "user":
        return redirect(url_for("login"))
        
    if db is None or not db.is_connected():
        flash("Database connection error.", "danger")
        return render_template("messages.html", messages=[])
        
    user_id = session.get("user_id")
    filter_status = request.args.get("status", "All")
    
    try:
        db.commit() # Force fresh read of messages
        if filter_status == "All":
            cursor.execute("SELECT * FROM contact_messages WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        else:
            cursor.execute("SELECT * FROM contact_messages WHERE user_id = %s AND status = %s ORDER BY created_at DESC", (user_id, filter_status))
            
        messages = cursor.fetchall()
        return render_template("messages.html", messages=messages, filter_status=filter_status)
    except mysql.connector.Error as e:
        flash("An error occurred loading your messages.", "danger")
        print(f"DB Error: {e}")
        return render_template("messages.html", messages=[], filter_status=filter_status)


# --- NEW FEATURES: History, Admin, Export, AI Chat ---

@app.route("/history")
@login_required
def history():
    if session.get("role") != "user":
        return redirect(url_for("login"))
    
    if db is None or not db.is_connected():
        flash("Database connection error.", "danger")
        return render_template("history.html", records=[])

    user_id = session["user_id"]
    search = request.args.get("search", "").lower()
    sort = request.args.get("sort", "desc")
    page = int(request.args.get("page", 1))
    per_page = 10
    
    try:
        order_sql = "DESC" if sort == "desc" else "ASC"
        cursor.execute(f"SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at {order_sql}", (user_id,))
        predictions = cursor.fetchall()
        # Process and calculate WQI
        records = []
        for p in predictions:
            wqi_score, wqi_cat = calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])
            rec = {
                "id": p["id"],
                "source": p["water_source"],
                "prediction_source": p.get("prediction_source", "Manual Entry"),
                "status": p["prediction"],
                "pollution_level": p["pollution_level"],
                "wqi": wqi_score,
                "wqi_category": wqi_cat,
                "timestamp": p["created_at"]
            }
            if search and search not in rec["source"].lower() and search not in rec["status"].lower():
                continue
            records.append(rec)
            
        total_records = len(records)
        total_pages = (total_records + per_page - 1) // per_page
        start = (page - 1) * per_page
        total_pages = (total_records + per_page - 1) // per_page
        
        cursor.execute('''
            SELECT a.*, i.full_name as inspector_name, i.phone as inspector_phone, i.email as inspector_email, i.district as inspector_district, ir.report_id, ir.findings,
                   (SELECT COUNT(*) FROM payments p WHERE p.report_id = ir.report_id AND p.status = 'Paid') as is_paid,
                   f.rating as feedback_rating, f.comments as feedback_comments
            FROM appointments a
            LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
            LEFT JOIN inspection_reports ir ON a.appointment_id = ir.appointment_id
            LEFT JOIN feedbacks f ON a.appointment_id = f.appointment_id
            WHERE a.user_id = %s
            ORDER BY a.created_at DESC
        ''', (user_id,))
        appointments = cursor.fetchall()
        import json
        for apt in appointments:
            if apt.get('findings'):
                try:
                    apt['parsed_findings'] = json.loads(apt['findings'])
                except Exception:
                    apt['parsed_findings'] = None

        
        return render_template("history.html", records=records[start:start+per_page], page=page, total_pages=total_pages, search=search, sort=sort, appointments=appointments)
    except Exception as e:
        flash(f"Error loading history: {e}", "danger")
        return render_template("history.html", records=[])

@app.route("/history/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_history(record_id):
    if session.get("role") != "user":
        return redirect(url_for("login"))
    try:
        cursor.execute("DELETE FROM predictions WHERE id = %s AND user_id = %s", (record_id, session["user_id"]))
        db.commit()
        flash("Record deleted successfully.", "success")
    except Exception as e:
        flash("Error deleting record.", "danger")
    return redirect(url_for("history"))

@app.route("/export/csv")
@login_required
def export_csv():
    if session.get("role") != "user": return redirect(url_for("login"))
    try:
        cursor.execute("SELECT water_source, prediction, pollution_level, dissolved_oxygen, ph, bod, nitrate, conductivity, created_at FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (session["user_id"],))
        preds = cursor.fetchall()
        
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(['Date', 'Source', 'Status', 'Pollution Level', 'WQI', 'WQI Category', 'DO', 'pH', 'BOD', 'Nitrate', 'Conductivity'])
        
        for p in preds:
            wqi, cat = calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])
            cw.writerow([p["created_at"], p["water_source"], p["prediction"], p["pollution_level"], wqi, cat, p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"]])
            
        output = Response(si.getvalue(), mimetype="text/csv")
        output.headers["Content-Disposition"] = "attachment; filename=aquaguard_history.csv"
        return output
    except Exception:
        flash("Error generating CSV.", "danger")
        return redirect(url_for("dashboard"))

@app.route("/export/excel")
@login_required
def export_excel():
    if session.get("role") != "user": return redirect(url_for("login"))
    try:
        cursor.execute("SELECT water_source, prediction, pollution_level, dissolved_oxygen, ph, bod, nitrate, conductivity, created_at FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (session["user_id"],))
        preds = cursor.fetchall()
        
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(['Date', 'Source', 'Status', 'Pollution Level', 'WQI', 'WQI Category', 'DO', 'pH', 'BOD', 'Nitrate', 'Conductivity'])
        
        for p in preds:
            wqi, cat = calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])
            cw.writerow([p["created_at"], p["water_source"], p["prediction"], p["pollution_level"], wqi, cat, p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"]])
            
        output = Response(si.getvalue(), mimetype="application/vnd.ms-excel")
        output.headers["Content-Disposition"] = "attachment; filename=aquaguard_history.csv"
        return output
    except Exception:
        flash("Error generating Excel file.", "danger")
        return redirect(url_for("dashboard"))



@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        cursor.execute("SELECT p.*, u.name as user_name FROM predictions p JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC LIMIT 5")
        predictions = cursor.fetchall()
        
        cursor.execute("SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 5")
        messages = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) as c FROM predictions")
        total_preds = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) as c FROM predictions WHERE prediction = 'SAFE'")
        safe_preds = cursor.fetchone()["c"]
        unsafe_preds = total_preds - safe_preds

        cursor.execute("SELECT COUNT(*) as c FROM users")
        total_users = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) as c FROM contact_messages")
        total_msgs = cursor.fetchone()["c"]

        # Avg WQI
        cursor.execute("SELECT dissolved_oxygen, ph, bod, nitrate, conductivity FROM predictions")
        all_preds = cursor.fetchall()
        wqi_sum = sum([calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])[0] for p in all_preds])
        avg_wqi = round(wqi_sum / total_preds, 1) if total_preds > 0 else 0
        
        records = []
        for p in predictions:
            wqi, cat = calculate_wqi(p["dissolved_oxygen"], p["ph"], p["bod"], p["nitrate"], p["conductivity"])
            records.append({
                "id": p["id"],
                "user_name": p["user_name"],
                "source": p["water_source"],
                "status": p["prediction"],
                "wqi": wqi,
                "timestamp": p["created_at"]
            })
            
        model_metrics = get_model_metrics()
        stats = {
            "total_preds": total_preds,
            "safe_preds": safe_preds,
            "unsafe_preds": unsafe_preds,
            "total_users": total_users,
            "total_msgs": total_msgs,
            "avg_wqi": avg_wqi,
            
            "model_metrics": model_metrics
        }
            
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number as user_phone, u.email as user_email, old_i.full_name as previous_inspector_name
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN inspectors old_i ON (a.rejected_inspector_id = old_i.inspector_id OR a.inspector_id = old_i.inspector_id)
            WHERE a.status IN ('Inspector Rejected', 'Rejected') OR a.assignment_status = 'Rejected'
            ORDER BY COALESCE(a.inspector_rejection_time, a.rejected_at, a.created_at) DESC
        ''')
        rejected_appointments = cursor.fetchall()
            
        return render_template("admin_dashboard.html", records=records, messages=messages, stats=stats, rejected_appointments=rejected_appointments)
    except Exception as e:
        flash(f"Admin Error: {e}", "danger")
        return render_template("admin_dashboard.html", records=[], messages=[], stats={}, rejected_appointments=[])

@app.route("/profile", methods=["GET", "POST"])
@login_required
def user_profile():
    if session.get("role") != "user": return redirect(url_for("login"))
    user_id = session.get("user_id")
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_profile":
            name = request.form.get("name", "").strip()
            mobile = request.form.get("mobile", "").strip()
            location = request.form.get("location", "").strip()
            
            if not name or not location:
                flash("Please fill in all required fields before submitting.", "danger")
            elif not is_valid_name(name):
                flash("Name must contain letters and spaces only.", "danger")
            elif mobile and not is_valid_phone(mobile):
                flash("Phone number must contain exactly 10 digits.", "danger")
            else:
                try:
                    cursor.execute("UPDATE users SET name=%s, mobile=%s, location=%s WHERE id=%s", (name, mobile, location, user_id))
                    db.commit()
                    session["name"] = name
                    flash("Profile updated successfully", "success")
                except Exception as e:
                    flash(f"Error updating profile: {e}", "danger")
                
        elif action == "update_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            
            if not is_valid_password(new_password):
                flash("Password must contain at least one letter and one number.", "danger")
            else:
                cursor.execute("SELECT password FROM users WHERE id=%s", (user_id,))
                u = cursor.fetchone()
                if u and check_password_hash(u["password"], current_password):
                    new_hash = generate_password_hash(new_password)
                    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_hash, user_id))
                    db.commit()
                    flash("Password updated successfully", "success")
                else:
                    flash("Incorrect current password", "danger")
                
        elif action == "update_picture":
            if 'profile_image' not in request.files:
                flash('No file part', 'danger')
                return redirect(request.url)
            file = request.files['profile_image']
            filename = file.filename
            if not filename:
                flash('No selected file', 'danger')
                return redirect(request.url)
            if allowed_file(filename):
                sec_filename = secure_filename(filename)
                sec_filename = f"{user_id}_{sec_filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], sec_filename))
                cursor.execute("UPDATE users SET profile_image=%s WHERE id=%s", (sec_filename, user_id))
                db.commit()
                flash("Profile picture updated", "success")
            else:
                flash("Invalid file type. Allowed: jpg, jpeg, png", "danger")
                
        return redirect(url_for("user_profile"))
        
    try:
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user_data = cursor.fetchone()
        
        # Get total predictions
        cursor.execute("SELECT COUNT(*) as c FROM predictions WHERE user_id=%s", (user_id,))
        total_predictions = cursor.fetchone()["c"]
        
        return render_template("profile.html", user=user_data, total_predictions=total_predictions)
    except Exception as e:
        flash(f"Error loading profile: {e}", "danger")
        return redirect(url_for("dashboard"))

@app.route("/admin/profile", methods=["GET", "POST"])
@login_required
def admin_profile():
    if session.get("role") != "admin": return redirect(url_for("login"))
    admin_id = session.get("user_id")
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_profile":
            name = request.form.get("name", "").strip()
            mobile = request.form.get("mobile", "").strip()
            
            if not name:
                flash("Please fill in all required fields before submitting.", "danger")
            elif not is_valid_name(name):
                flash("Name must contain letters and spaces only.", "danger")
            elif mobile and not is_valid_phone(mobile):
                flash("Phone number must contain exactly 10 digits.", "danger")
            else:
                try:
                    cursor.execute("UPDATE users SET name=%s, mobile=%s WHERE id=%s", (name, mobile, admin_id))
                    db.commit()
                    session["name"] = name
                    flash("Profile updated successfully", "success")
                except Exception as e:
                    flash(f"Error updating profile: {e}", "danger")
                
        elif action == "update_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            
            if not is_valid_password(new_password):
                flash("Password must contain at least one letter and one number.", "danger")
            else:
                cursor.execute("SELECT password FROM users WHERE id=%s", (admin_id,))
                admin_user = cursor.fetchone()
                if admin_user and check_password_hash(admin_user["password"], current_password):
                    new_hash = generate_password_hash(new_password)
                    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_hash, admin_id))
                    db.commit()
                    flash("Password updated successfully", "success")
                else:
                    flash("Incorrect current password", "danger")
                
        elif action == "update_picture":
            if 'profile_image' not in request.files:
                flash('No file part', 'danger')
                return redirect(request.url)
            file = request.files['profile_image']
            filename = file.filename
            if not filename:
                flash('No selected file', 'danger')
                return redirect(request.url)
            if allowed_file(filename):
                sec_filename = secure_filename(filename)
                sec_filename = f"{admin_id}_{sec_filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], sec_filename))
                cursor.execute("UPDATE users SET profile_image=%s WHERE id=%s", (sec_filename, admin_id))
                db.commit()
                flash("Profile picture updated", "success")
            else:
                flash("Invalid file type. Allowed: jpg, jpeg, png", "danger")
                
        return redirect(url_for("admin_profile"))
        
    try:
        cursor.execute("SELECT * FROM users WHERE id=%s", (admin_id,))
        admin_data = cursor.fetchone()
        
        if not admin_data:
            session.clear()
            flash("Admin profile not found. Please log in again.", "danger")
            return redirect(url_for("login"))
            
        return render_template("admin_profile.html", admin=admin_data)
    except Exception as e:
        flash(f"Error loading profile: {e}", "danger")
        return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete/<int:record_id>", methods=["POST"])
@login_required
def admin_delete(record_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        cursor.execute("DELETE FROM predictions WHERE id = %s", (record_id,))
        db.commit()
        flash("Record deleted", "success")
    except Exception:
        flash("Error deleting", "danger")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin logged out", "success")
    return redirect(url_for("login"))

@app.route("/admin/messages")
@login_required
def admin_messages():
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        db.commit() # Force fresh read of messages
        cursor.execute("SELECT * FROM contact_messages ORDER BY created_at DESC")
        messages = cursor.fetchall()
        return render_template("admin_messages.html", messages=messages)
    except Exception as e:
        flash(f"Admin Error: {e}", "danger")
        return render_template("admin_messages.html", messages=[])

@app.route("/admin/messages/delete/<int:msg_id>", methods=["POST"])
@login_required
def admin_delete_message(msg_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        cursor.execute("DELETE FROM contact_messages WHERE id = %s", (msg_id,))
        db.commit()
        flash("Message deleted", "success")
    except Exception:
        flash("Error deleting message", "danger")
    return redirect(url_for("admin_messages"))

@app.route("/admin/messages/reply/<int:msg_id>", methods=["POST"])
@login_required
def admin_reply_message(msg_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    reply_text = request.form.get("reply_message")
    if not reply_text:
        flash("Reply message cannot be empty.", "danger")
        return redirect(url_for("admin_messages"))
        
    try:
        cursor.execute("SELECT * FROM contact_messages WHERE id = %s", (msg_id,))
        msg = cursor.fetchone()
        if not msg:
            flash("Message not found.", "danger")
            return redirect(url_for("admin_messages"))
            
        # Update database
        cursor.execute(
            "UPDATE contact_messages SET status = 'Replied', reply_message = %s, reply_date = %s WHERE id = %s",
            (reply_text, datetime.now(), msg_id)
        )
        db.commit()
        
        # Send Email
        subject = f"Re: {msg['subject']} - AquaGuard AI Support"
        email_body = f"Hello {msg['name']},\n\nThank you for reaching out to us regarding '{msg['subject']}'.\n\n{reply_text}\n\nBest regards,\nAquaGuard AI Team"
        
        msg_email = Message(subject, recipients=[msg['email']], body=email_body)
        mail.send(msg_email)
        
        flash("Reply sent successfully.", "success")
    except Exception as e:
        flash(f"Error sending reply: {e}", "danger")
        
    return redirect(url_for("admin_messages"))

SYSTEM_INSTRUCTION = """You are AquaGuard AI, a Water Quality Assistant.
Your expertise is limited strictly to: Water Quality, Water Safety, Water Quality Index (WQI), pH, TDS, Turbidity, Conductivity, Dissolved Oxygen (DO), Biological Oxygen Demand (BOD), Chemical Oxygen Demand (COD), Water Hardness, Nitrate, Fluoride, Chloride, Sulfate, Water Pollution, Water Contamination, Water Purification, Drinking Water Standards, WHO Guidelines, AI Water Quality Predictions, Prediction Confidence Scores, Water Quality Reports, Environmental Monitoring, Rivers, Lakes, Wells, Groundwater, Tap Water, Industrial Water.
If the user asks any question related to these topics, provide a clear, accurate, professional, and conversational response.
If the user asks questions outside the water quality domain (such as movies, sports, celebrities, coding, mathematics, politics, shopping, travel, jokes, etc.), you MUST NOT answer them. Instead, reply EXACTLY with this string: "I'm AquaGuard AI, your Water Quality Assistant. My expertise is limited to water quality, water safety, water testing, environmental monitoring, and AI-based water quality predictions. I can't answer questions outside these topics. Please ask me something related to water quality or your prediction results."
If the user's question is unclear, respond EXACTLY with: "I'm sorry, I couldn't understand your question. Please ask a question related to water quality, water testing, water safety, or your AquaGuard AI prediction."
If a user asks about their prediction result:
- Explain why the water was classified as SAFE or UNSAFE.
- Explain the important parameters that influenced the prediction.
- Provide practical recommendations for improving water quality if the result is UNSAFE.
- If the result is SAFE, provide tips for maintaining good water quality.
Never make up facts. If the required information is unavailable, politely state that you don't have enough information.
Always maintain a professional, friendly, and helpful tone.
"""

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    req_json = request.get_json(silent=True) or {}
    msg = req_json.get("message", "").strip()
    if not msg:
        return jsonify({"response": "I'm sorry, I couldn't understand your question. Please ask a question related to water quality, water testing, water safety, or your AquaGuard AI prediction."})

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "YOUR_GROQ_API_KEY":
        return jsonify({"response": "Groq API key is missing. Please configure GROQ_API_KEY in the .env file."})
        
    try:
        client = Groq(api_key=api_key)
        
        # Initialize chat history if not exists
        if "chat_history" not in session:
            session["chat_history"] = []
            
        history = session["chat_history"]
        
        # Inject recent prediction context if user is logged in
        context = ""
        user_id = session.get("user_id")
        if user_id and len(history) == 0:
            cursor.execute("SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
            latest_pred = cursor.fetchone()
            if latest_pred:
                context = f"[SYSTEM CONTEXT: The user recently performed a water quality prediction with these parameters: pH={latest_pred['ph']}, Temperature={latest_pred['temperature']}, DO={latest_pred['dissolved_oxygen']}, BOD={latest_pred['bod']}, Nitrate={latest_pred['nitrate']}, Conductivity={latest_pred['conductivity']}. The AI classified the water as '{latest_pred['prediction']}'. Keep this in mind if they ask about their prediction.]\n\n"
        
        messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        if context:
            messages.append({"role": "system", "content": context})
            
        for h in history:
            # Map Gemini's 'model' to Groq's 'assistant' for backward compatibility
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["content"]})
            
        messages.append({"role": "user", "content": msg})
        
        chat_completion = client.chat.completions.create(
            messages=messages, # type: ignore
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.7,
            max_tokens=1024
        )
        reply = chat_completion.choices[0].message.content
        
        # Save to session (limit history to last 10 messages/20 turns to avoid cookie overflow)
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": reply})
        if len(history) > 20:
            history = history[-20:]
        session["chat_history"] = history
        
        return jsonify({"response": reply})
    except Exception as e:
        print("\n--- GROQ API EXCEPTION ---")
        traceback.print_exc()
        print("--------------------------\n")
        
        error_msg = str(e).lower()
        if "invalid_api_key" in error_msg or "authentication" in error_msg:
            return jsonify({"response": "Authentication Error: The provided Groq API key is invalid. Please check your .env file."})
        elif "rate_limit" in error_msg or "429" in error_msg:
            return jsonify({"response": "Rate Limit Exceeded: The AI is currently receiving too many requests. Please try again in a moment."})
        elif "model_decommissioned" in error_msg or "invalid_model" in error_msg or "does not exist" in error_msg:
            return jsonify({"response": "Model Error: The configured AI model is invalid or decommissioned. Please check GROQ_MODEL in your environment settings."})
        elif "connection" in error_msg or "timeout" in error_msg or "network" in error_msg:
            return jsonify({"response": "Network Error: Unable to connect to the Groq AI service. Please check your internet connection."})
        else:
            return jsonify({"response": f"An error occurred while processing your request: {str(e)}"})



# --- INSPECTOR APPOINTMENT SYSTEM ROUTES ---

@app.route('/inspector/login', methods=['GET', 'POST'])
def inspector_login():
    return redirect(url_for('login'))

@app.route('/inspector/logout')
def inspector_logout():
    session.clear()
    flash("Inspector logged out successfully", "success")
    return redirect(url_for('login'))

@app.route('/inspector/dashboard')
@login_required
def inspector_dashboard():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    try:
        insp_id = session.get("user_id")
        
        # Get stats
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE (inspector_id=%s OR assigned_inspector_id=%s) AND status IN ('Pending Inspector Approval', 'Pending', 'Assigned')", (insp_id, insp_id))
        pending = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE (inspector_id=%s OR assigned_inspector_id=%s) AND status IN ('Accepted', 'Approved', 'In Progress')", (insp_id, insp_id))
        accepted = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE (inspector_id=%s OR assigned_inspector_id=%s) AND status='Completed'", (insp_id, insp_id))
        completed = cursor.fetchone()['c']
        
        # Get Field Inspection Appointments ONLY
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number, u.email, ir.report_id
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN predictions p ON a.prediction_id = p.id
            LEFT JOIN inspection_reports ir ON a.appointment_id = ir.appointment_id
            WHERE (a.inspector_id = %s OR a.assigned_inspector_id = %s)
              AND a.inspection_type IN ('Field Inspection', 'Both Online & Field Inspection')
            ORDER BY a.created_at DESC
        ''', (insp_id, insp_id))
        field_appointments = cursor.fetchall()
        
        # Get Online Inspection Appointments ONLY
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number, u.email, p.water_source, p.dissolved_oxygen, p.ph, p.bod, p.nitrate, p.conductivity, p.prediction, p.pollution_level, ir.report_id
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN predictions p ON a.prediction_id = p.id
            LEFT JOIN inspection_reports ir ON a.appointment_id = ir.appointment_id
            WHERE (a.inspector_id = %s OR a.assigned_inspector_id = %s)
              AND a.inspection_type IN ('Online Inspection', 'Both Online & Field Inspection')
            ORDER BY a.created_at DESC
        ''', (insp_id, insp_id))
        online_appointments = cursor.fetchall()
        
        for apt in online_appointments:
            if apt.get('ph') is not None and apt.get('dissolved_oxygen') is not None:
                wqi, wqi_cat = calculate_wqi(apt.get("dissolved_oxygen", 0), apt.get("ph", 7), apt.get("bod", 0), apt.get("nitrate", 0), apt.get("conductivity", 0))
                apt['wqi'] = wqi
                apt['wqi_cat'] = wqi_cat

        stats = {
            'pending': pending, 
            'accepted': accepted, 
            'completed': completed,
            'field_count': len(field_appointments),
            'online_count': len(online_appointments)
        }
        return render_template('inspector_dashboard.html', 
                               field_appointments=field_appointments, 
                               online_appointments=online_appointments, 
                               stats=stats)
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")
        return redirect(url_for("login"))


@app.route('/inspector/online-inspections')
@login_required
def inspector_online_inspections():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    try:
        insp_id = session.get("user_id")
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number, u.email, p.water_source, p.dissolved_oxygen, p.ph, p.bod, p.nitrate, p.conductivity, p.prediction, p.pollution_level, ir.report_id
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN predictions p ON a.prediction_id = p.id
            LEFT JOIN inspection_reports ir ON a.appointment_id = ir.appointment_id
            WHERE (a.inspector_id = %s OR a.assigned_inspector_id = %s)
              AND a.inspection_type IN ('Online Inspection', 'Both Online & Field Inspection')
            ORDER BY a.created_at DESC
        ''', (insp_id, insp_id))
        online_appointments = cursor.fetchall()
        
        for apt in online_appointments:
            if apt.get('ph') is not None and apt.get('dissolved_oxygen') is not None:
                wqi, wqi_cat = calculate_wqi(apt.get("dissolved_oxygen", 0), apt.get("ph", 7), apt.get("bod", 0), apt.get("nitrate", 0), apt.get("conductivity", 0))
                apt['wqi'] = wqi
                apt['wqi_cat'] = wqi_cat

        return render_template('inspector_online_inspection.html', appointments=online_appointments)
    except Exception as e:
        flash(f"Error loading online inspections: {e}", "danger")
        return redirect(url_for("inspector_dashboard"))


@app.route('/inspector/field-inspections')
@login_required
def inspector_field_inspections():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    try:
        insp_id = session.get("user_id")
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number, u.email, ir.report_id
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN predictions p ON a.prediction_id = p.id
            LEFT JOIN inspection_reports ir ON a.appointment_id = ir.appointment_id
            WHERE (a.inspector_id = %s OR a.assigned_inspector_id = %s)
              AND a.inspection_type IN ('Field Inspection', 'Both Online & Field Inspection')
            ORDER BY a.created_at DESC
        ''', (insp_id, insp_id))
        field_appointments = cursor.fetchall()

        return render_template('inspector_field_inspections.html', appointments=field_appointments)
    except Exception as e:
        flash(f"Error loading field inspections: {e}", "danger")
        return redirect(url_for("inspector_dashboard"))

@app.route('/inspector/action/<int:apt_id>', methods=['POST'])
@login_required
def inspector_action(apt_id):
    if session.get("role") != "inspector": return redirect(url_for("login"))
    action = request.form.get("action")
    target_mode = request.form.get("target_mode") # 'online' or 'field' or None
    insp_id = session.get("user_id")
    try:
        db.commit() # Force fresh read to avoid stale data
        cursor.execute("SELECT * FROM appointments WHERE appointment_id=%s", (apt_id,))
        apt = cursor.fetchone()
        
        if not apt:
            flash("Appointment not found", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        if apt.get('inspector_id') != insp_id and apt.get('assigned_inspector_id') != insp_id:
            flash("Appointment is not assigned to this inspector", "danger")
            return redirect(url_for('inspector_dashboard'))

        current_status = apt.get('status') or 'Pending'

        if action in ("approve", "accept"):
            if current_status == 'Completed':
                flash("Cannot approve an already completed inspection.", "warning")
                return redirect(request.referrer or url_for('inspector_dashboard'))
            if current_status in ('Rejected', 'Inspector Rejected'):
                flash("Cannot approve a rejected inspection.", "warning")
                return redirect(request.referrer or url_for('inspector_dashboard'))

            cursor.execute("""
                UPDATE appointments 
                SET status='Approved', 
                    assignment_status='Approved', 
                    inspector_approval_time=NOW(), 
                    accepted_at=NOW() 
                WHERE appointment_id=%s AND (inspector_id=%s OR assigned_inspector_id=%s)
            """, (apt_id, insp_id, insp_id))

            if target_mode == 'online' or apt.get('inspection_type') == 'Online Inspection':
                cursor.execute("UPDATE appointments SET online_status='Approved' WHERE appointment_id=%s", (apt_id,))
            elif target_mode == 'field' or apt.get('inspection_type') == 'Field Inspection':
                cursor.execute("UPDATE appointments SET field_status='Approved' WHERE appointment_id=%s", (apt_id,))
            else:
                cursor.execute("UPDATE appointments SET online_status='Approved', field_status='Approved' WHERE appointment_id=%s", (apt_id,))

            db.commit()
            flash("Inspection assignment approved successfully. Click 'Start Inspection' when ready.", "success")
            
            # Email Notification to User
            cursor.execute("SELECT u.email, u.name FROM appointments a JOIN users u ON a.user_id = u.id WHERE a.appointment_id=%s", (apt_id,))
            u = cursor.fetchone()
            if u:
                try:
                    msg = Message(f"Inspection Approved - AquaGuard AI", recipients=[u['email']], 
                                  body=f"Hello {u['name']},\nYour water quality inspection appointment has been approved by inspector {session.get('name')}.")
                    mail.send(msg)
                except: pass

            # Stay on current page so inspector can explicitly click "Start Inspection"
            return redirect(request.referrer or url_for('inspector_dashboard'))

        elif action == "reject":
            if current_status == 'Completed':
                flash("Cannot reject a completed inspection.", "warning")
                return redirect(request.referrer or url_for('inspector_dashboard'))

            rejection_reason = request.form.get("rejection_reason", "").strip() or "No reason specified"
            
            cursor.execute("""
                UPDATE appointments 
                SET status='Inspector Rejected', 
                    assignment_status='Rejected', 
                    inspector_rejection_time=NOW(), 
                    rejected_at=NOW(), 
                    rejection_reason=%s, 
                    rejected_inspector_id=%s, 
                    inspector_id=NULL, 
                    assigned_inspector_id=NULL 
                WHERE appointment_id=%s
            """, (rejection_reason, insp_id, apt_id))

            if target_mode == 'online':
                cursor.execute("UPDATE appointments SET online_status='Rejected' WHERE appointment_id=%s", (apt_id,))
            elif target_mode == 'field':
                cursor.execute("UPDATE appointments SET field_status='Rejected' WHERE appointment_id=%s", (apt_id,))

            db.commit()
            flash("Inspection assignment rejected. Admin has been notified.", "warning")
            return redirect(request.referrer or url_for('inspector_dashboard'))

        elif action in ("start_inspection", "start"):
            if current_status in ('Pending Inspector Approval', 'Pending', 'Pending Approval', 'Inspector Rejected', 'Rejected') and apt.get('assignment_status') not in ('Approved', 'Accepted'):
                flash("You must approve the inspection assignment before starting inspection.", "danger")
                return redirect(request.referrer or url_for('inspector_dashboard'))

            cursor.execute("""
                UPDATE appointments 
                SET status='In Progress', 
                    assignment_status='In Progress', 
                    inspection_started_time=NOW() 
                WHERE appointment_id=%s
            """, (apt_id,))

            if target_mode == 'online' or (apt.get('inspection_type') == 'Online Inspection'):
                cursor.execute("UPDATE appointments SET online_status='In Progress' WHERE appointment_id=%s", (apt_id,))
            elif target_mode == 'field' or (apt.get('inspection_type') == 'Field Inspection'):
                cursor.execute("UPDATE appointments SET field_status='In Progress' WHERE appointment_id=%s", (apt_id,))

            db.commit()
            flash("Inspection started. Proceeding to inspection page.", "info")

            if target_mode == 'online' or (apt.get('inspection_type') == 'Online Inspection'):
                return redirect(url_for('inspection_details', apt_id=apt_id))
            else:
                return redirect(url_for('inspector_field_inspection', appointment_id=apt_id))

    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for('inspector_dashboard'))


def finalize_appointment_report(apt_id, inspector_id, online_findings=None):
    import json
    # Fetch fresh appointment
    cursor.execute("SELECT * FROM appointments WHERE appointment_id = %s", (apt_id,))
    apt = cursor.fetchone()
    if not apt:
        return
        
    inspection_type = apt['inspection_type']
    online_status = apt['online_status']
    field_status = apt['field_status']
    
    # Calculate overall status
    is_finished = False
    if inspection_type == 'Online Inspection' and online_status == 'Completed':
        is_finished = True
    elif inspection_type == 'Field Inspection' and field_status == 'Completed':
        is_finished = True
    elif inspection_type == 'Both Online & Field Inspection' and online_status == 'Completed' and field_status == 'Completed':
        is_finished = True
        
    status = apt['status']
    if is_finished:
        status = 'Completed'
    else:
        if inspection_type == 'Both Online & Field Inspection' and (online_status == 'Completed' or field_status == 'Completed'):
            status = 'Partially Completed'
            
    # Update appointment status
    if is_finished:
        cursor.execute("UPDATE appointments SET status=%s, completed_at=NOW() WHERE appointment_id=%s", (status, apt_id))
    else:
        cursor.execute("UPDATE appointments SET status=%s WHERE appointment_id=%s", (status, apt_id))
    db.commit()
    
    # Deal with inspection_reports
    cursor.execute("SELECT * FROM inspection_reports WHERE appointment_id = %s", (apt_id,))
    rep = cursor.fetchone()
    
    # Gather findings JSON
    findings_data = {}
    recommendations = ""
    
    if rep and rep['findings']:
        try:
            findings_data = json.loads(rep['findings'])
            recommendations = rep['recommendations']
        except:
            pass
            
    if online_findings:
        findings_data.update(online_findings)
        recommendations = online_findings.get('final_recommendation') or recommendations
        
    findings_json = json.dumps(findings_data)
    
    if is_finished:
        # Build ReportLab PDF
        # We need user and prediction
        cursor.execute("SELECT * FROM predictions WHERE id=%s", (apt['prediction_id'],))
        pred = cursor.fetchone()
        
        cursor.execute("SELECT * FROM users WHERE id=%s", (apt['user_id'],))
        user = cursor.fetchone()
        
        # Let's find inspector details
        cursor.execute("SELECT * FROM inspectors WHERE inspector_id=%s", (inspector_id,))
        inspector = cursor.fetchone()
        inspector_name = inspector['full_name'] if inspector else "Assigned Inspector"
        inspector_desc = inspector['designation'] if inspector else "Water Quality Expert"
        
        # Query field observations if completed
        cursor.execute("SELECT * FROM field_inspections WHERE appointment_id=%s", (apt_id,))
        field_obs = cursor.fetchone()
        
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        import textwrap
        
        pdf_filename = f"inspection_{apt_id}_{int(datetime.now().timestamp())}.pdf"
        reports_dir = os.path.join(app.root_path, 'static', 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        pdf_path = os.path.join(reports_dir, pdf_filename)
        
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, f"AquaGuard Official Inspection Report")
        c.setFont("Helvetica", 10)
        c.drawString(50, 725, f"Report ID: INS-{apt_id} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(50, 710, f"Inspector: {inspector_name} ({inspector_desc})")
        c.drawString(50, 695, f"Client Name: {user['name'] if user else 'Unknown'}")
        c.drawString(50, 680, f"Water Source: {pred['water_source'] if pred else 'N/A'} (Type: {inspection_type})")
        
        y = 650
        
        # 1. Prediction details (if available and Online is required)
        if pred and (inspection_type == 'Online Inspection' or inspection_type == 'Both Online & Field Inspection'):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "1. AquaGuard AI Diagnostic & Laboratory Values")
            c.setFont("Helvetica", 9)
            c.drawString(50, y-15, f"AI Status prediction: {pred['prediction']}")
            
            c.drawString(50, y-30, f"Temperature: {pred['temperature']} °C")
            c.drawString(250, y-30, f"Dissolved Oxygen: {pred['dissolved_oxygen']} mg/L")
            c.drawString(50, y-45, f"pH Level: {pred['ph']}")
            c.drawString(250, y-45, f"BOD: {pred['bod']} mg/L")
            c.drawString(50, y-60, f"Conductivity: {pred['conductivity']} uS/cm")
            c.drawString(250, y-60, f"Nitrate: {pred['nitrate']} mg/L")
            c.drawString(50, y-75, f"Faecal Coliform: {pred['faecal_coliform']} MPN/100ml")
            c.drawString(250, y-75, f"Total Coliform: {pred['total_coliform']} MPN/100ml")
            y -= 95
            
        # 2. Online Inspection Findings
        if online_status == 'Completed' and findings_data:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "2. Online Inspection Recommendations")
            y -= 15
            
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, f"Final Recommendation: {findings_data.get('final_recommendation', 'N/A')}")
            c.drawString(280, y, f"Purification Method: {findings_data.get('purification_method', 'N/A')}")
            y -= 20
            
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Recommended Method Details / Remarks:")
            c.setFont("Helvetica", 9)
            y -= 15
            for line in textwrap.wrap(findings_data.get('inspector_comments') or '', width=95):
                c.drawString(50, y, line)
                y -= 15
                if y < 60:
                    c.showPage()
                    y = 730
                    c.setFont("Helvetica", 9)
                    
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Precautions:")
            c.setFont("Helvetica", 9)
            y -= 15
            for line in textwrap.wrap(findings_data.get('recommended_precautions') or '', width=95):
                c.drawString(50, y, line)
                y -= 15
                if y < 60:
                    c.showPage()
                    y = 730
                    c.setFont("Helvetica", 9)
                    
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, f"Follow-up Required: {findings_data.get('follow_up_required', 'No')}")
            if findings_data.get('follow_up_required') == 'Yes':
                c.drawString(250, y, f"Follow-up Date: {findings_data.get('follow_up_date', 'N/A')}")
            y -= 25
            if y < 60:
                c.showPage()
                y = 730
                
        # 3. Field Inspection Findings
        if field_status == 'Completed' and field_obs:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "3. Physical Field Observations")
            y -= 20
            
            c.setFont("Helvetica", 9)
            c.drawString(50, y, f"Water Appearance: {field_obs.get('water_appearance')}")
            c.drawString(220, y, f"Water Colour: {field_obs.get('water_colour')}")
            c.drawString(380, y, f"Water Odour: {field_obs.get('water_odour')}")
            y -= 15
            
            c.drawString(50, y, f"Visible Contamination: {field_obs.get('visible_contamination')}")
            c.drawString(220, y, f"Nearby Pollution: {field_obs.get('nearby_pollution')}")
            c.drawString(380, y, f"Drainage/Leakage: {field_obs.get('drainage_leakage')}")
            y -= 15
            
            c.drawString(50, y, f"Sample Collected: {field_obs.get('sample_collected')}")
            if field_obs.get('sample_collected') == 'Yes':
                c.drawString(220, y, f"Sample ID: {field_obs.get('sample_id')}")
                c.drawString(380, y, f"Lab Sent: {field_obs.get('sample_sent_to_lab')}")
            y -= 20
            if y < 60:
                c.showPage()
                y = 730
                c.setFont("Helvetica", 9)
                
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Field Assessment Summary:")
            c.setFont("Helvetica", 9)
            y -= 15
            for line in textwrap.wrap(field_obs.get('inspection_summary') or '', width=95):
                c.drawString(50, y, line)
                y -= 15
                if y < 60:
                    c.showPage()
                    y = 730
                    c.setFont("Helvetica", 9)
                    
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Recommended Action:")
            c.setFont("Helvetica", 9)
            y -= 15
            for line in textwrap.wrap(field_obs.get('recommended_action') or '', width=95):
                c.drawString(50, y, line)
                y -= 15
                if y < 60:
                    c.showPage()
                    y = 730
                    c.setFont("Helvetica", 9)
                    
            if not online_status == 'Completed':
                recommendations = field_obs.get('inspector_assessment') or 'Completed Field Inspection'
                
        c.save()
        db_pdf_path = f"/static/reports/{pdf_filename}"
        
        if rep:
            cursor.execute(
                "UPDATE inspection_reports SET findings=%s, recommendations=%s, report_file=%s, inspection_date=%s WHERE report_id=%s",
                (findings_json, recommendations, db_pdf_path, datetime.now().date(), rep['report_id'])
            )
        else:
            cursor.execute(
                "INSERT INTO inspection_reports (appointment_id, inspector_id, findings, recommendations, inspection_date, report_file) VALUES (%s, %s, %s, %s, %s, %s)",
                (apt_id, inspector_id, findings_json, recommendations, datetime.now().date(), db_pdf_path)
            )
        db.commit()
        
        # Email user
        try:
            msg = Message(f"Inspection Completed - Report Available", recipients=[user['email']], 
                          body=f"Hello {user['name']},\nYour inspection has been fully completed. You can pay the fee (if applicable) and view the report in your dashboard.")
            mail.send(msg)
        except: pass
        
    else:
        # Partially Completed
        if rep:
            cursor.execute(
                "UPDATE inspection_reports SET findings=%s, recommendations=%s, inspection_date=%s WHERE report_id=%s",
                (findings_json, recommendations, datetime.now().date(), rep['report_id'])
            )
        else:
            cursor.execute(
                "INSERT INTO inspection_reports (appointment_id, inspector_id, findings, recommendations, inspection_date, report_file) VALUES (%s, %s, %s, %s, %s, %s)",
                (apt_id, inspector_id, findings_json, recommendations, datetime.now().date(), '')
            )
        db.commit()

@app.route('/inspector/inspection/<int:apt_id>')
@login_required
def inspection_details(apt_id):
    role = session.get("role")
    if role not in ("inspector", "admin", "user"): return redirect(url_for("login"))
    try:
        if role == "admin":
            cursor.execute('''
                SELECT a.*, u.name as user_name, u.email, u.phone_number, u.mobile, p.*,
                       i.full_name as inspector_name, i.district as inspector_district
                FROM appointments a 
                JOIN users u ON a.user_id = u.id 
                JOIN predictions p ON a.prediction_id = p.id
                LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
                WHERE a.appointment_id = %s
            ''', (apt_id,))
        elif role == "user":
            cursor.execute('''
                SELECT a.*, u.name as user_name, u.email, u.phone_number, u.mobile, p.*,
                       i.full_name as inspector_name, i.district as inspector_district
                FROM appointments a 
                JOIN users u ON a.user_id = u.id 
                JOIN predictions p ON a.prediction_id = p.id
                LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
                WHERE a.appointment_id = %s AND a.user_id = %s
            ''', (apt_id, session['user_id']))
        else:
            cursor.execute('''
                SELECT a.*, u.name as user_name, u.email, u.phone_number, u.mobile, p.*,
                       i.full_name as inspector_name, i.district as inspector_district
                FROM appointments a 
                JOIN users u ON a.user_id = u.id 
                JOIN predictions p ON a.prediction_id = p.id
                LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
                WHERE a.appointment_id = %s AND a.inspector_id = %s
            ''', (apt_id, session['user_id']))
            
        details = cursor.fetchone()
        
        fallback_redirect = 'admin_appointments' if role == 'admin' else ('history' if role == 'user' else 'inspector_dashboard')

        if not details:
            flash("Inspection not found or unauthorized.", "danger")
            return redirect(url_for(fallback_redirect))
            
        if details['inspection_type'] == 'Field Inspection':
            flash("Online Inspection is not available for this Field-Only inspection.", "warning")
            return redirect(url_for(fallback_redirect))
            
        if role == 'inspector' and details['status'] not in ('In Progress', 'Partially Completed', 'Completed', 'Accepted', 'Approved'):
            flash("You must start the inspection before viewing details or filling measurement data.", "warning")
            return redirect(url_for('inspector_dashboard'))
            
        wqi, wqi_cat = calculate_wqi(details["dissolved_oxygen"], details["ph"], details["bod"], details["nitrate"], details["conductivity"])
        details['wqi'] = wqi
        details['wqi_cat'] = wqi_cat
        
        # Load existing findings if present
        cursor.execute("SELECT * FROM inspection_reports WHERE appointment_id = %s LIMIT 1", (apt_id,))
        report_row = cursor.fetchone()
        if report_row and report_row.get('findings'):
            try:
                import json
                if isinstance(report_row['findings'], str):
                    details['existing_findings'] = json.loads(report_row['findings'])
                else:
                    details['existing_findings'] = report_row['findings']
            except:
                details['existing_findings'] = {}
        
        details = make_json_serializable(details)
        return render_template('inspection_details.html', details=details)
    except Exception as e:
        flash(f"Error loading details: {e}", "danger")
        fallback_redirect = 'admin_appointments' if session.get("role") == 'admin' else ('history' if session.get("role") == 'user' else 'inspector_dashboard')
        return redirect(url_for(fallback_redirect))

@app.route('/inspector/complete/<int:apt_id>', methods=['POST'])
@login_required
def complete_inspection(apt_id):
    if session.get("role") != "inspector": return redirect(url_for("login"))
    
    # Check appointment
    try:
        db.commit() # Force fresh read to avoid stale data
        cursor.execute("SELECT * FROM appointments WHERE appointment_id=%s", (apt_id,))
        apt = cursor.fetchone()
        
        if not apt:
            flash("Appointment not found", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        if apt['inspector_id'] != session['user_id']:
            flash("Appointment is not assigned to this inspector", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        if apt['status'] == 'Completed':
            flash("Appointment has already been completed", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        if apt['status'] == 'Rejected':
            flash("Appointment has been cancelled", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        if apt['inspection_type'] == 'Field Inspection':
            flash("Online Inspection is not available for this Field-Only inspection.", "warning")
            return redirect(url_for('inspector_dashboard'))
            
        if apt['status'] not in ('In Progress', 'Partially Completed'):
            flash("Please start the inspection before completing it.", "danger")
            return redirect(url_for('inspector_dashboard'))
            
        cursor.execute("SELECT * FROM predictions WHERE id=%s", (apt['prediction_id'],))
        pred = cursor.fetchone()
        
        cursor.execute("SELECT * FROM users WHERE id=%s", (apt['user_id'],))
        user = cursor.fetchone()
        
        # Gather all form data
        recommended_precautions = request.form.get('recommended_precautions')
        purification_method = request.form.get('purification_method')
        inspector_comments = request.form.get('inspector_comments')
        final_recommendation = request.form.get('final_recommendation')
        follow_up_required = request.form.get('follow_up_required')
        follow_up_date = request.form.get('follow_up_date') if follow_up_required == 'Yes' else None
        
        # Validation
        if not recommended_precautions or not purification_method or not final_recommendation or not follow_up_required:
            flash("Please complete all required fields before submitting the inspection.", "warning")
            return redirect(url_for('inspection_details', apt_id=apt_id))
        if follow_up_required == 'Yes' and not follow_up_date:
            flash("Please complete all required fields before submitting the inspection.", "warning")
            return redirect(url_for('inspection_details', apt_id=apt_id))
            
        # Build JSON findings
        findings_data = {
            'recommended_precautions': recommended_precautions,
            'purification_method': purification_method,
            'inspector_comments': inspector_comments,
            'final_recommendation': final_recommendation,
            'follow_up_required': follow_up_required,
            'follow_up_date': follow_up_date
        }
        
        # Save to DB substatus
        cursor.execute("UPDATE appointments SET online_status='Completed' WHERE appointment_id=%s", (apt_id,))
        db.commit()
        
        # Call finalizer to compile PDF if fully done
        finalize_appointment_report(apt_id, session['user_id'], online_findings=findings_data)
        
        flash("Online inspection part completed successfully.", "success")
    except Exception as e:
        flash(f"Error completing inspection: {e}", "danger")
        
    return redirect(url_for('inspector_dashboard'))


@app.route('/book_appointment/<int:prediction_id>', methods=['GET', 'POST'])
@login_required
def book_appointment(prediction_id):
    if session.get("role") != "user": return redirect(url_for("login"))
    
    try:
        cursor.execute("SELECT * FROM predictions WHERE id=%s AND user_id=%s", (prediction_id, session['user_id']))
        pred = cursor.fetchone()
        if not pred or pred['prediction'] == 'SAFE':
            flash("Invalid prediction or water is already safe.", "danger")
            return redirect(url_for('history'))
            
        if request.method == 'POST':
            address = request.form.get("address")
            issue = request.form.get("issue")
            inspection_type = request.form.get("inspection_type", "Online Inspection")
            
            lat_str = request.form.get("latitude")
            lng_str = request.form.get("longitude")
            latitude = float(lat_str) if lat_str and lat_str.strip() else None
            longitude = float(lng_str) if lng_str and lng_str.strip() else None
            
            online_d = request.form.get("online_date") or request.form.get("date")
            online_t = request.form.get("online_time") or request.form.get("time")
            field_d = request.form.get("field_date") or request.form.get("date")
            field_t = request.form.get("field_time") or request.form.get("time")
            
            if inspection_type == 'Online Inspection':
                if not online_d or not online_t:
                    flash("Please select both Online Preferred Date and Time.", "danger")
                    return redirect(url_for('book_appointment', prediction_id=prediction_id))
                apt_date = online_d
                apt_time = online_t
                online_date_val = str(online_d)
                online_time_val = str(online_t)
                field_date_val = None
                field_time_val = None
                online_status = 'Pending'
                field_status = 'N/A'
            elif inspection_type == 'Field Inspection':
                if not field_d or not field_t:
                    flash("Please select both Field Preferred Date and Time.", "danger")
                    return redirect(url_for('book_appointment', prediction_id=prediction_id))
                apt_date = field_d
                apt_time = field_t
                online_date_val = None
                online_time_val = None
                field_date_val = str(field_d)
                field_time_val = str(field_t)
                online_status = 'N/A'
                field_status = 'Pending'
            else: # Both Online & Field Inspection
                if not online_d or not online_t:
                    flash("Please select Online Preferred Date and Time.", "danger")
                    return redirect(url_for('book_appointment', prediction_id=prediction_id))
                if not field_d or not field_t:
                    flash("Please select Field Preferred Date and Time.", "danger")
                    return redirect(url_for('book_appointment', prediction_id=prediction_id))
                    
                apt_date = online_d
                apt_time = online_t
                online_date_val = str(online_d)
                online_time_val = str(online_t)
                field_date_val = str(field_d)
                field_time_val = str(field_t)
                online_status = 'Pending'
                field_status = 'Pending'
            
            cursor.execute(
                """INSERT INTO appointments 
                   (user_id, prediction_id, appointment_date, appointment_time, online_date, online_time, field_date, field_time, address, issue_description, inspection_type, online_status, field_status, latitude, longitude) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (session['user_id'], prediction_id, apt_date, apt_time, online_date_val, online_time_val, field_date_val, field_time_val, address, issue, inspection_type, online_status, field_status, latitude, longitude)
            )
            db.commit()
            
            # Send Email safely
            try:
                msg_body = f"Hello {session['name']},\nYour appointment request ({inspection_type}) has been received."
                if inspection_type == 'Both Online & Field Inspection':
                    msg_body += f"\nOnline Inspection: {online_date_val} at {online_time_val}\nField Inspection: {field_date_val} at {field_time_val}"
                else:
                    msg_body += f"\nScheduled Date: {apt_date} at {apt_time}"
                msg_body += "\nStatus: Pending assignment."

                msg = Message(f"Appointment Request Received - AquaGuard AI", recipients=[session['email']], body=msg_body)
                mail.send(msg)
            except: pass
            
            flash("Appointment booked successfully. We will assign an inspector soon.", "success")
            return redirect(url_for('history'))
            
        wqi, wqi_cat = calculate_wqi(pred["dissolved_oxygen"], pred["ph"], pred["bod"], pred["nitrate"], pred["conductivity"])
        today = datetime.now().strftime('%Y-%m-%d')
        return render_template('book_appointment.html', prediction=pred, wqi=wqi, wqi_cat=wqi_cat, today=today)
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('history'))


@app.route('/admin/inspectors', methods=['GET', 'POST'])
@login_required
def admin_inspectors():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    if request.method == 'POST':
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        district = request.form.get("district")
        designation = request.form.get("designation")
        if not full_name or not email or not phone or not password or not district or not designation:
            flash("Please fill in all required fields before submitting.", "danger")
            return redirect(url_for('admin_inspectors'))
            
        if not is_valid_name(full_name):
            flash("Name must contain letters and spaces only.", "danger")
            return redirect(url_for('admin_inspectors'))
            
        if not is_valid_email(email):
            flash("Please enter a valid Gmail address ending with @gmail.com.", "danger")
            return redirect(url_for('admin_inspectors'))
            
        if not is_valid_phone(phone):
            flash("Phone number must contain exactly 10 digits.", "danger")
            return redirect(url_for('admin_inspectors'))
            
        if not is_valid_password(password):
            flash("Password must contain at least one letter and one number.", "danger")
            return redirect(url_for('admin_inspectors'))
            
        try:
            hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO inspectors (full_name, email, phone, password, district, designation) VALUES (%s, %s, %s, %s, %s, %s)",
                (full_name, email, phone, hashed, district, designation)
            )
            db.commit()
            flash("Inspector added successfully.", "success")
        except Exception as e:
            flash(f"Error adding inspector: {e}", "danger")
            
        return redirect(url_for('admin_inspectors'))
        
    try:
        cursor.execute("SELECT * FROM inspectors ORDER BY created_at DESC")
        inspectors = cursor.fetchall()
        return render_template('admin_inspectors.html', inspectors=inspectors)
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/inspectors/delete/<int:inspector_id>', methods=['POST'])
@app.route('/admin/inspectors/deactivate/<int:inspector_id>', methods=['POST'])
@app.route('/admin/inspectors/reject/<int:inspector_id>', methods=['POST'])
@login_required
def admin_delete_inspector(inspector_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        cursor.execute("SELECT status FROM inspectors WHERE inspector_id=%s", (inspector_id,))
        insp = cursor.fetchone()
        if insp:
            curr_status = insp.get('status', 'Active')
            new_status = 'Rejected' if curr_status == 'Pending' else 'Inactive'
            cursor.execute("UPDATE inspectors SET status=%s WHERE inspector_id=%s", (new_status, inspector_id))
            db.commit()
            flash(f"Inspector status updated to {new_status}. Historical records preserved.", "success")
        else:
            flash("Inspector not found.", "danger")
    except Exception as e:
        flash(f"Error updating inspector status: {e}", "danger")
    return redirect(url_for('admin_inspectors'))

@app.route('/admin/inspectors/activate/<int:inspector_id>', methods=['POST'])
@login_required
def admin_activate_inspector(inspector_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        cursor.execute("UPDATE inspectors SET status='Active' WHERE inspector_id=%s", (inspector_id,))
        db.commit()
        flash("Inspector activated successfully.", "success")
    except Exception as e:
        flash(f"Error activating inspector: {e}", "danger")
    return redirect(url_for('admin_inspectors'))

@app.route('/admin/appointments', methods=['GET', 'POST'])
@login_required
def admin_appointments():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    if request.method == 'POST':
        apt_id = request.form.get("appointment_id")
        insp_id = request.form.get("inspector_id")
        if not insp_id or not str(insp_id).strip():
            flash("Please select an inspector.", "danger")
            return redirect(url_for('admin_appointments'))
            
        try:
            cursor.execute("SELECT inspector_id, full_name, status FROM inspectors WHERE inspector_id=%s", (insp_id,))
            insp = cursor.fetchone()
            if not insp or (insp.get('status') and insp.get('status') != 'Active'):
                flash("Selected inspector is not currently active.", "danger")
                return redirect(url_for('admin_appointments'))
                
            cursor.execute("""
                UPDATE appointments 
                SET inspector_id=%s, 
                    assigned_inspector_id=%s, 
                    status='Pending Inspector Approval', 
                    assignment_status='Pending Inspector Approval', 
                    assigned_at=NOW(), 
                    inspector_approval_time=NULL, 
                    inspector_rejection_time=NULL 
                WHERE appointment_id=%s
            """, (insp_id, insp_id, apt_id))
            db.commit()
            
            flash("Inspector assigned successfully. Awaiting inspector approval.", "success")
            return redirect(url_for('admin_appointments'))
        except Exception as e:
            flash("Unable to assign inspector. Please try again.", "danger")
        return redirect(url_for('admin_appointments'))
        
    try:
        cursor.execute('''
            SELECT a.*, u.name as user_name, u.phone_number, i.full_name as inspector_name, i.district as inspector_district,
                   p.status as raw_payment_status
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id 
            LEFT JOIN (
                SELECT appointment_id, status, MAX(id) as max_id
                FROM payments
                GROUP BY appointment_id
            ) latest_p ON a.appointment_id = latest_p.appointment_id
            LEFT JOIN payments p ON latest_p.max_id = p.id
            ORDER BY a.created_at DESC
        ''')
        appointments = cursor.fetchall()

        for apt in appointments:
            raw_p = apt.get('raw_payment_status')
            if not raw_p:
                apt['payment_status'] = 'NOT PAID'
            else:
                raw_upper = str(raw_p).strip().upper()
                if raw_upper in ('PAID', 'SUCCESS', 'COMPLETED'):
                    apt['payment_status'] = 'PAID'
                elif raw_upper in ('PENDING', 'PROCESSING'):
                    apt['payment_status'] = 'PENDING'
                elif raw_upper in ('FAILED', 'CANCELLED', 'REJECTED'):
                    apt['payment_status'] = 'FAILED'
                else:
                    apt['payment_status'] = 'NOT PAID'
        
        cursor.execute('''
            SELECT a.*, u.name as user_name, old_i.full_name as previous_inspector_name
            FROM appointments a 
            JOIN users u ON a.user_id = u.id 
            LEFT JOIN inspectors old_i ON (a.rejected_inspector_id = old_i.inspector_id OR a.inspector_id = old_i.inspector_id)
            WHERE a.status IN ('Inspector Rejected', 'Rejected') OR a.assignment_status = 'Rejected'
            ORDER BY COALESCE(a.inspector_rejection_time, a.rejected_at, a.created_at) DESC
        ''')
        rejected_appointments = cursor.fetchall()
        
        cursor.execute("SELECT * FROM inspectors WHERE status='Active'")
        inspectors = cursor.fetchall()
        
        return render_template('admin_appointments.html', appointments=appointments, inspectors=inspectors, rejected_appointments=rejected_appointments)
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/feedbacks')
@login_required
def admin_feedbacks():
    if session.get("role") != "admin":
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))
        
    try:
        # Search & Sort filters
        search = request.args.get("search", "").strip().lower()
        sort = request.args.get("sort", "newest")
        
        # Calculate summary metrics (overall)
        cursor.execute("SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM feedbacks")
        summary = cursor.fetchone()
        total_feedback = summary['total'] or 0
        avg_rating = round(summary['avg_rating'], 2) if summary['avg_rating'] is not None else 0.0
        
        # NPS Calculation
        cursor.execute("SELECT recommendation, COUNT(*) as count FROM feedbacks GROUP BY recommendation")
        nps_raw = cursor.fetchall()
        nps_counts = {'Yes': 0, 'Maybe': 0, 'No': 0}
        for row in nps_raw:
            if row['recommendation'] in nps_counts:
                nps_counts[row['recommendation']] = row['count']
                
        promoters = nps_counts['Yes']
        passives = nps_counts['Maybe']
        detractors = nps_counts['No']
        
        nps_score = 0
        if total_feedback > 0:
            nps_score = round(((promoters - detractors) / total_feedback) * 100, 1)
            
        # Category analysis counts
        cursor.execute("SELECT categories FROM feedbacks WHERE categories IS NOT NULL")
        cats_rows = cursor.fetchall()
        cat_counts = {
            'Punctuality': 0,
            'Technical Expertise': 0,
            'Communication': 0,
            'Report Clarity': 0,
            'System Usability': 0
        }
        for row in cats_rows:
            parts = [p.strip() for p in row['categories'].split(',')]
            for part in parts:
                if part in cat_counts:
                    cat_counts[part] += 1
                    
        # Details list query
        order_by_sql = "f.created_at DESC"
        if sort == "oldest":
            order_by_sql = "f.created_at ASC"
        elif sort == "highest_rating":
            order_by_sql = "f.rating DESC, f.created_at DESC"
        elif sort == "lowest_rating":
            order_by_sql = "f.rating ASC, f.created_at DESC"
            
        cursor.execute(f"""
            SELECT f.*, u.name as user_name, a.appointment_date, i.full_name as inspector_name
            FROM feedbacks f
            JOIN users u ON f.user_id = u.id
            JOIN appointments a ON f.appointment_id = a.appointment_id
            LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
            ORDER BY {order_by_sql}
        """)
        feedbacks = cursor.fetchall()
        
        # client filtering by search
        filtered_feedbacks = []
        for fb in feedbacks:
            if search:
                user_match = search in fb['user_name'].lower()
                insp_match = search in (fb['inspector_name'] or '').lower()
                comments_match = search in (fb['comments'] or '').lower()
                cats_match = search in (fb['categories'] or '').lower()
                recom_match = search in (fb['recommendation'] or '').lower()
                if not (user_match or insp_match or comments_match or cats_match or recom_match):
                    continue
            filtered_feedbacks.append(fb)
            
        metrics = {
            'total': total_feedback,
            'avg_rating': avg_rating,
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
            'nps_score': nps_score,
            'categories': cat_counts
        }
        
        return render_template('admin_feedbacks.html', feedbacks=filtered_feedbacks, metrics=metrics, search=search, sort=sort)
    except Exception as e:
        flash(f"Error loading feedbacks: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

@app.route('/feedback/<int:apt_id>', methods=['GET', 'POST'])
@login_required
def submit_feedback(apt_id):
    if session.get("role") != "user":
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))
        
    try:
        # Fetch appointment details
        cursor.execute("""
            SELECT a.*, u.name as user_name, i.full_name as inspector_name 
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            LEFT JOIN inspectors i ON a.inspector_id = i.inspector_id
            WHERE a.appointment_id = %s AND a.user_id = %s
        """, (apt_id, session['user_id']))
        apt = cursor.fetchone()
        
        if not apt:
            flash("Appointment not found or unauthorized.", "danger")
            return redirect(url_for('history'))
            
        if apt['status'] != 'Completed':
            flash("You can only submit feedback for completed inspections.", "warning")
            return redirect(url_for('history'))
            
        # Check if feedback already exists to prevent duplicate submissions
        cursor.execute("SELECT feedback_id FROM feedbacks WHERE appointment_id = %s AND user_id = %s", (apt_id, session['user_id']))
        existing = cursor.fetchone()
        if existing:
            flash("You have already submitted feedback for this inspection.", "info")
            return redirect(url_for('history'))
            
        if request.method == 'POST':
            rating = request.form.get("rating")
            if not rating:
                flash("Please select a rating.", "danger")
                return render_template('feedback.html', apt=apt)
                
            rating = int(rating)
            if rating < 1 or rating > 5:
                flash("Invalid rating selected.", "danger")
                return render_template('feedback.html', apt=apt)
                
            categories_list = request.form.getlist("categories")
            categories_str = ", ".join(categories_list) if categories_list else None
            comments = request.form.get("comments", "").strip() or None
            recommendation = request.form.get("recommendation", "Maybe")
            
            cursor.execute("""
                INSERT INTO feedbacks (appointment_id, user_id, rating, categories, comments, recommendation)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (apt_id, session['user_id'], rating, categories_str, comments, recommendation))
            db.commit()
            
            flash("Thank you for your feedback! Your response helps us improve AquaGuard AI.", "success")
            return redirect(url_for('history'))
            
        return render_template('feedback.html', apt=apt)
    except Exception as e:
        flash(f"Error handling feedback: {e}", "danger")
        return redirect(url_for('history'))

# --- UPI PAYMENT GATEWAY INTEGRATION ---
UPI_ID = os.getenv("UPI_ID", "aquaguard@upi")
UPI_MERCHANT_NAME = os.getenv("UPI_MERCHANT_NAME", "AquaGuard AI")

@app.route('/payment/<int:report_id>')
@login_required
def payment(report_id):
    if session.get("role") != "user":
        flash("Please log in to view this page.", "danger")
        return redirect(url_for('login'))
        
    try:
        # Verify ownership and completion
        cursor.execute("""
            SELECT r.report_id, a.appointment_id, a.status 
            FROM inspection_reports r 
            JOIN appointments a ON r.appointment_id = a.appointment_id 
            WHERE r.report_id=%s AND a.user_id=%s
        """, (report_id, session['user_id']))
        report = cursor.fetchone()
        if not report:
            flash("Report not found or unauthorized.", "danger")
            return redirect(url_for('history'))
        if report['status'] != 'Completed':
            flash("Report is locked because inspection is not fully completed.", "danger")
            return redirect(url_for('history'))
            
        # Check if already paid
        cursor.execute("SELECT transaction_id FROM payments WHERE report_id = %s AND status = 'Paid'", (report_id,))
        paid = cursor.fetchone()
        if paid:
            return redirect(url_for('payment_success', report_id=report_id))
            
        return render_template(
            'payment.html', 
            report_id=report_id, 
            amount=50, 
            upi_id=UPI_ID, 
            upi_merchant_name=UPI_MERCHANT_NAME
        )
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('history'))

@app.route('/process_payment/<int:report_id>', methods=['POST'])
@login_required
@csrf.exempt
def process_payment(report_id):
    if session.get("role") != "user":
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json(silent=True) or request.form
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    payment_method = data.get('payment_method', 'Google Pay').strip()
    
    # Server-side Validations
    if not name or not re.match(r"^[a-zA-Z\s]+$", name) or len(name) < 3:
        return jsonify({'error': 'Invalid name. Must contain only letters and spaces, min 3 chars.'}), 400
        
    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'error': 'Invalid email format.'}), 400
        
    if not phone or not re.match(r"^\d{10}$", phone):
        return jsonify({'error': 'Phone number must be exactly 10 digits.'}), 400
        
    try:
        # Verify ownership and completion
        cursor.execute("""
            SELECT r.report_id, a.appointment_id, a.status 
            FROM inspection_reports r 
            JOIN appointments a ON r.appointment_id = a.appointment_id 
            WHERE r.report_id=%s AND a.user_id=%s
        """, (report_id, session['user_id']))
        report = cursor.fetchone()
        if not report:
            return jsonify({'error': 'Report not found or unauthorized.'}), 404
        if report['status'] != 'Completed':
            return jsonify({'error': 'Report is locked because inspection is not fully completed.'}), 400
            
        # Check duplicate
        cursor.execute("SELECT id FROM payments WHERE report_id = %s AND status = 'Paid'", (report_id,))
        if cursor.fetchone():
            return jsonify({'redirect_url': url_for('payment_success', report_id=report_id)}), 200
            
        amount_in_rupees = 50
        timestamp_sec = int(datetime.now().timestamp())
        txn_ref = f"UPI_REP_{report_id}_{timestamp_sec}"
        
        # Insert or update pending payment record
        cursor.execute("SELECT id FROM payments WHERE report_id = %s AND status = 'Pending'", (report_id,))
        pending_payment = cursor.fetchone()
        if pending_payment:
            cursor.execute("""
                UPDATE payments 
                SET transaction_id = %s, amount = %s, payment_method = %s, payment_date = NOW(), appointment_id = %s
                WHERE id = %s
            """, (txn_ref, amount_in_rupees, payment_method, report['appointment_id'], pending_payment['id']))
        else:
            cursor.execute("""
                INSERT INTO payments (user_id, amount, status, appointment_id, report_id, payment_method, transaction_id, payment_date) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (session['user_id'], amount_in_rupees, 'Pending', report['appointment_id'], report_id, payment_method, txn_ref))
        db.commit()

        from urllib.parse import quote
        tn = quote(f"AquaGuard Report Access #{report_id}")
        pn = quote(UPI_MERCHANT_NAME)
        upi_uri = f"upi://pay?pa={UPI_ID}&pn={pn}&am={amount_in_rupees:.2f}&cu=INR&tn={tn}&tr={txn_ref}"
        gpay_uri = f"tez://upi/pay?pa={UPI_ID}&pn={pn}&am={amount_in_rupees:.2f}&cu=INR&tn={tn}&tr={txn_ref}"
        phonepe_uri = f"phonepe://pay?pa={UPI_ID}&pn={pn}&am={amount_in_rupees:.2f}&cu=INR&tn={tn}&tr={txn_ref}"

        return jsonify({
            'success': True,
            'txn_ref': txn_ref,
            'amount': amount_in_rupees,
            'currency': 'INR',
            'upi_id': UPI_ID,
            'upi_merchant_name': UPI_MERCHANT_NAME,
            'payment_method': payment_method,
            'upi_uri': upi_uri,
            'gpay_uri': gpay_uri,
            'phonepe_uri': phonepe_uri,
            'report_id': report_id
        }), 200
    except Exception as e:
        print("UPI order creation exception:", e)
        return jsonify({'error': f'Payment failed to initialize: {str(e)}'}), 500

@app.route('/verify_upi_payment', methods=['POST'])
@login_required
@csrf.exempt
def verify_upi_payment():
    if session.get("role") != "user":
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        data = request.get_json(silent=True) or request.form
        report_id = data.get('report_id')
        transaction_ref = data.get('transaction_ref') or data.get('txn_ref')
        utr_number = (data.get('utr_number') or data.get('utr') or '').strip()
        payment_method = data.get('payment_method', 'UPI').strip()
        action = data.get('action', 'verify')
        
        if not report_id:
            return jsonify({'status': 'failed', 'message': 'Missing report ID.'}), 400
            
        report_id = int(report_id)
        
        if action == 'cancel':
            cursor.execute("SELECT id FROM payments WHERE report_id = %s AND status = 'Pending'", (report_id,))
            p_row = cursor.fetchone()
            if p_row:
                cursor.execute("UPDATE payments SET status = 'Failed' WHERE id = %s", (p_row['id'],))
                db.commit()
            return jsonify({'status': 'cancelled', 'message': 'Payment cancelled by user.'}), 200

        if not utr_number or len(utr_number) < 6:
            return jsonify({
                'status': 'failed', 
                'message': 'Please enter a valid 12-digit UPI UTR / Reference Number from your payment app.'
            }), 400

        cursor.execute("""
            SELECT r.report_id, a.appointment_id 
            FROM inspection_reports r 
            JOIN appointments a ON r.appointment_id = a.appointment_id 
            WHERE r.report_id=%s AND a.user_id=%s
        """, (report_id, session['user_id']))
        report_row = cursor.fetchone()
        if not report_row:
            return jsonify({'status': 'failed', 'message': 'Report not found or unauthorized.'}), 404
            
        cursor.execute("SELECT id FROM payments WHERE (transaction_id = %s OR report_id = %s) AND status != 'Paid'", (transaction_ref, report_id))
        payment_row = cursor.fetchone()
        
        final_txn_id = utr_number if utr_number else (transaction_ref or f"UPI_{report_id}_{int(datetime.now().timestamp())}")
        
        if payment_row:
            cursor.execute("""
                UPDATE payments 
                SET status = 'Paid', transaction_id = %s, payment_method = %s, payment_date = NOW() 
                WHERE id = %s
            """, (final_txn_id, payment_method, payment_row['id']))
        else:
            cursor.execute("""
                INSERT INTO payments (user_id, amount, status, appointment_id, report_id, payment_method, transaction_id, payment_date)
                VALUES (%s, %s, %s, (SELECT appointment_id FROM inspection_reports WHERE report_id = %s), %s, %s, %s, NOW())
            """, (session['user_id'], 50, 'Paid', report_id, report_id, payment_method, final_txn_id))
        db.commit()
        
        flash("Payment completed and verified successfully!", "success")
        return jsonify({
            'status': 'success',
            'redirect_url': url_for('payment_success', report_id=report_id)
        }), 200
    except Exception as e:
        print("UPI payment verification error:", e)
        return jsonify({'status': 'failed', 'message': f'Verification error: {str(e)}'}), 500

@app.route('/payment_success/<int:report_id>')
@login_required
def payment_success(report_id):
    if session.get("role") != "user":
        return redirect(url_for('login'))
        
    try:
        cursor.execute("""
            SELECT amount, transaction_id, payment_method, payment_date 
            FROM payments 
            WHERE report_id = %s AND user_id = %s AND status = 'Paid'
            ORDER BY id DESC LIMIT 1
        """, (report_id, session['user_id']))
        payment = cursor.fetchone()
        if not payment:
            flash("No successful payment found for this report.", "danger")
            return redirect(url_for('history'))
            
        return render_template('payment_success.html', report_id=report_id, payment=payment)
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('history'))

@app.route('/download_inspection_report/<int:report_id>')
@login_required
def download_inspection_report(report_id):
    role = session.get("role")
    if not role: return redirect(url_for('login'))
    try:
        report = None
        if role == 'user':
            cursor.execute("""
                SELECT r.report_file, a.status 
                FROM inspection_reports r 
                JOIN appointments a ON r.appointment_id = a.appointment_id 
                WHERE r.report_id=%s AND a.user_id=%s
                AND (SELECT COUNT(*) FROM payments p WHERE p.report_id = r.report_id AND p.status = 'Paid') > 0
            """, (report_id, session['user_id']))
            report = cursor.fetchone()
            if not report:
                flash("Report not found, incomplete, or unpaid.", "danger")
                return redirect(url_for('history'))
            if report['status'] != 'Completed':
                flash("Report is locked because inspection is not fully completed.", "danger")
                return redirect(url_for('history'))
        elif role == 'inspector':
            cursor.execute("SELECT report_file FROM inspection_reports WHERE report_id=%s AND inspector_id=%s", (report_id, session['user_id']))
            report = cursor.fetchone()
        elif role == 'admin':
            flash("Access denied. Admin does not have permission to view or download detailed inspection reports.", "danger")
            return redirect(url_for('admin_appointments'))
            
        if not report:
            flash("Report not found or unauthorized.", "danger")
            if role == 'user': return redirect(url_for('history'))
            elif role == 'inspector': return redirect(url_for('inspector_dashboard'))
            else: return redirect(url_for('admin_appointments'))
            
        path = os.path.join(app.root_path, report['report_file'].lstrip('/'))
        from flask import send_file
        return send_file(path, as_attachment=True)
    except Exception as e:
        flash(f"Error downloading: {e}", "danger")
        return redirect(url_for('index'))


# --- DYNAMIC WATER QUALITY REPORT GENERATOR (REPORTLAB) ---

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String, Wedge, Circle, Line

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []

    def showPage(self):
        self.pages.append(dict(self.__dict__))
        self._startPage() # type: ignore

    def save(self):
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            self.draw_footer(page_count)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(54, 30, "Generated by AquaGuard AI – AI-Based Water Quality Monitoring System")
        self.drawRightString(612 - 54, 30, f"Page {self._pageNumber} of {page_count}") # type: ignore
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 42, 612 - 54, 42)
        self.restoreState()

def check_parameter_status(name, value):
    if value is None:
        return 'Normal'
    try:
        val = float(value)
    except ValueError:
        return 'Normal'
        
    if name == 'pH':
        return 'Optimal' if 6.5 <= val <= 8.5 else 'Suboptimal'
    elif name == 'Dissolved Oxygen':
        return 'Optimal' if val >= 5.0 else 'Suboptimal'
    elif name == 'BOD':
        return 'Optimal' if val <= 5.0 else 'Suboptimal'
    elif name == 'Nitrate':
        return 'Optimal' if val <= 45.0 else 'Suboptimal'
    elif name == 'Conductivity':
        return 'Optimal' if val <= 1000.0 else 'Suboptimal'
    elif name == 'Faecal Streptococci':
        return 'Optimal' if val <= 100.0 else 'Suboptimal'
    elif name == 'Faecal Coliform':
        return 'Optimal' if val <= 50.0 else 'Suboptimal'
    elif name == 'Total Coliform':
        return 'Optimal' if val <= 500.0 else 'Suboptimal'
    elif name == 'Temperature':
        return 'Optimal' if 10.0 <= val <= 35.0 else 'Suboptimal'
    else:
        return 'Normal'

def draw_pie_chart(safe, unsafe):
    draw = Drawing(200, 100)
    total = safe + unsafe
    if total == 0:
        safe_pct, unsafe_pct = 0, 0
        safe_angle = 180
    else:
        safe_pct = (safe / total) * 100
        unsafe_pct = (unsafe / total) * 100
        safe_angle = (safe / total) * 360
        
    cy, cx, r = 50, 50, 40
    
    if total == 0:
        draw.add(Circle(cx, cy, r, fillColor=colors.HexColor("#e2e8f0"), strokeColor=colors.HexColor("#cbd5e1")))
    elif safe == total:
        draw.add(Circle(cx, cy, r, fillColor=colors.HexColor("#0d9488"), strokeColor=colors.white, strokeWidth=1))
    elif unsafe == total:
        draw.add(Circle(cx, cy, r, fillColor=colors.HexColor("#ef4444"), strokeColor=colors.white, strokeWidth=1))
    else:
        draw.add(Wedge(cx, cy, r, 0, safe_angle, fillColor=colors.HexColor("#0d9488"), strokeColor=colors.white, strokeWidth=1))
        draw.add(Wedge(cx, cy, r, safe_angle, 360, fillColor=colors.HexColor("#ef4444"), strokeColor=colors.white, strokeWidth=1))
        
    draw.add(Rect(110, 60, 10, 10, fillColor=colors.HexColor("#0d9488"), strokeColor=None)) # type: ignore
    draw.add(String(125, 61, f"SAFE: {safe} ({safe_pct:.0f}%)", fontSize=8, fontName="Helvetica-Bold", fillColor=colors.HexColor("#1e293b")))
    
    draw.add(Rect(110, 36, 10, 10, fillColor=colors.HexColor("#ef4444"), strokeColor=None)) # type: ignore
    draw.add(String(125, 37, f"UNSAFE: {unsafe} ({unsafe_pct:.0f}%)", fontSize=8, fontName="Helvetica-Bold", fillColor=colors.HexColor("#1e293b")))
    
    return draw

def draw_wqi_trend_chart(wqi_trend):
    draw = Drawing(240, 100)
    if not wqi_trend:
        draw.add(String(120, 50, "No trend data available", fontSize=9, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#94a3b8")))
        return draw
        
    w_max = max(wqi_trend)
    w_min = min(wqi_trend)
    
    margin_y = 15
    ylim_max = int(w_max + margin_y)
    ylim_min = int(max(0, w_min - margin_y))
    if ylim_max == ylim_min:
        ylim_max = ylim_min + 100
        
    y_range = ylim_max - ylim_min
    
    for y_val in [ylim_min, ylim_min + y_range/2, ylim_max]:
        y_pos = 15 + ((y_val - ylim_min) / y_range) * 65
        draw.add(Line(25, y_pos, 225, y_pos, strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=0.5))
        draw.add(String(20, y_pos - 3, f"{int(y_val)}", fontSize=7, fontName="Helvetica", textAnchor="end", fillColor=colors.HexColor("#64748b")))
        
    points = []
    n_points = len(wqi_trend)
    if n_points > 1:
        x_step = 190 / (n_points - 1)
        for i, val in enumerate(wqi_trend):
            x = 30 + i * x_step
            y = 15 + ((val - ylim_min) / y_range) * 65
            points.append((x, y))
            draw.add(Circle(x, y, 2.5, fillColor=colors.HexColor("#8b5cf6"), strokeColor=colors.white, strokeWidth=0.5))
            draw.add(String(x, y + 5, f"{int(val)}", fontSize=7, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#1e293b")))
            
        for i in range(n_points - 1):
            x1, y1 = points[i]
            x2, y2 = points[i+1]
            draw.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#8b5cf6"), strokeWidth=1.2))
            
        for i in range(n_points):
            x, y = points[i]
            if n_points <= 5 or i % 2 == 0 or i == n_points - 1:
                draw.add(String(x, 5, f"T-{n_points - i}", fontSize=7, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#475569")))
    elif n_points == 1:
        x = 125
        y = 50
        draw.add(Circle(x, y, 3, fillColor=colors.HexColor("#8b5cf6"), strokeColor=colors.white, strokeWidth=0.5))
        draw.add(String(x, y + 6, f"{int(wqi_trend[0])}", fontSize=8, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#1e293b")))
        draw.add(String(x, 5, "T-1", fontSize=7, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#475569")))
        
    return draw

def draw_bar_chart(monthly_data):
    draw = Drawing(450, 100)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    m_max = max(monthly_data) if monthly_data else 0
    if m_max == 0: m_max = 5
    
    for y_val in [0, m_max/2, m_max]:
        y_pos = 15 + (y_val / m_max) * 65
        draw.add(Line(30, y_pos, 420, y_pos, strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=0.5))
        draw.add(String(25, y_pos - 3, f"{int(y_val)}", fontSize=7, fontName="Helvetica", textAnchor="end", fillColor=colors.HexColor("#64748b")))
        
    bar_w = 16
    gap = 14
    for i, val in enumerate(monthly_data):
        x_pos = 35 + i * (bar_w + gap)
        h = (val / m_max) * 65 if m_max > 0 else 0
        if h > 0:
            draw.add(Rect(x_pos, 15, bar_w, h, fillColor=colors.HexColor("#0284c7"), strokeColor=None)) # type: ignore
        draw.add(String(x_pos + bar_w/2, 5, months[i], fontSize=7, fontName="Helvetica", textAnchor="middle", fillColor=colors.HexColor("#475569")))
        
    return draw

def generate_pdf_report_buffer(prediction, user_record, all_user_preds, field_inspection, model_metrics):
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.HexColor("#0f172a"),
        alignment=0,
        spaceAfter=2
    )
    
    subtitle_style = ParagraphStyle(
        "ReportSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#0d9488"),
        alignment=0,
        spaceAfter=15
    )
    
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569"),
        alignment=2
    )
    
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        "TableBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b")
    )
    
    body_bold = ParagraphStyle(
        "TableBodyBold",
        parent=body_style,
        fontName="Helvetica-Bold"
    )
    
    alert_style = ParagraphStyle(
        "ResultAlertText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#1e293b")
    )
    
    story = []
    
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inspection_date_str = str(field_inspection['inspection_date']) if field_inspection else "N/A"
    
    header_left = [
        Paragraph("AQUAGUARD AI", title_style),
        Paragraph("WATER QUALITY ASSESSMENT REPORT", subtitle_style)
    ]
    header_right = [
        Paragraph(
            f"<b>Report ID:</b> WQR-{prediction['id']:06d}<br/>"
            f"<b>Generated:</b> {current_time_str}<br/>"
            f"<b>Inspection Date:</b> {inspection_date_str}",
            meta_style
        )
    ]
    
    header_table = Table([[header_left, header_right]], colWidths=[280, 224])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 0),
        ('LINEBELOW', (0,0), (-1,-1), 1.5, colors.HexColor('#0d9488')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))
    
    cust_name = user_record['name'] if user_record else "Unknown Customer"
    cust_email = user_record['email'] if user_record else "N/A"
    inspector_name = field_inspection['inspector_name'] if field_inspection else "N/A"
    
    meta_rows = [
        [
            Paragraph("<b>Customer Name:</b> " + cust_name, body_style),
            Paragraph("<b>Water Source:</b> " + prediction['water_source'], body_style)
        ],
        [
            Paragraph("<b>Contact Email:</b> " + cust_email, body_style),
            Paragraph("<b>Data Source:</b> " + prediction.get('prediction_source', 'Manual Entry'), body_style)
        ]
    ]
    if field_inspection:
        meta_rows.append([
            Paragraph("<b>Field Inspector:</b> " + inspector_name, body_style),
            Paragraph("<b>Inspection Date/Time:</b> " + f"{field_inspection['inspection_date']} {field_inspection['inspection_time']}", body_style)
        ])
        
    meta_table = Table(meta_rows, colWidths=[250, 254])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))
    
    total_preds = len(all_user_preds)
    safe_preds = sum(1 for p in all_user_preds if p['prediction'] == 'SAFE')
    unsafe_preds = total_preds - safe_preds
    
    wqi_sum = []
    for p in all_user_preds:
        if all(p.get(k) is not None for k in ['dissolved_oxygen', 'ph', 'bod', 'nitrate', 'conductivity']):
            wqi_v, _ = calculate_wqi(p['dissolved_oxygen'], p['ph'], p['bod'], p['nitrate'], p['conductivity'])
            wqi_sum.append(wqi_v)
    avg_wqi = round(sum(wqi_sum) / len(wqi_sum), 1) if wqi_sum else 0.0
    
    model_accuracy = model_metrics.get('accuracy', 98.0)
    
    summary_cells = [
        Paragraph(f"<font size=14 color='#0f172a'><b>{total_preds}</b></font><br/><font size=7.5 color='#475569'><b>Total Analyses</b></font>", body_style),
        Paragraph(f"<font size=14 color='#0d9488'><b>{safe_preds}</b></font><br/><font size=7.5 color='#475569'><b>Safe Status</b></font>", body_style),
        Paragraph(f"<font size=14 color='#ef4444'><b>{unsafe_preds}</b></font><br/><font size=7.5 color='#475569'><b>Unsafe Status</b></font>", body_style),
        Paragraph(f"<font size=14 color='#8b5cf6'><b>{avg_wqi}</b></font><br/><font size=7.5 color='#475569'><b>Average WQI</b></font>", body_style),
        Paragraph(f"<font size=14 color='#0284c7'><b>{model_accuracy}%</b></font><br/><font size=7.5 color='#475569'><b>Model Acc.</b></font>", body_style)
    ]
    summary_table = Table([summary_cells], colWidths=[100, 101, 101, 101, 101])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0f9ff')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#bae6fd')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bae6fd')),
    ]))
    
    story.append(Paragraph("Monitoring Summary Histograms Overview", section_title_style))
    story.append(summary_table)
    story.append(Spacer(1, 12))
    
    p_wqi, p_wqi_cat = calculate_wqi(
        prediction['dissolved_oxygen'],
        prediction['ph'],
        prediction['bod'],
        prediction['nitrate'],
        prediction['conductivity']
    )
    
    is_safe = prediction['prediction'] == 'SAFE'
    bg_color = colors.HexColor('#d1fae5') if is_safe else colors.HexColor('#fee2e2')
    border_color = colors.HexColor('#34d399') if is_safe else colors.HexColor('#fca5a5')
    text_color = '#065f46' if is_safe else '#991b1b'
    status_label = "SAFE" if is_safe else "UNSAFE"
    
    status_text = f"<font size=14 color='{text_color}'><b>AI ASSESSMENT: {status_label}</b></font>"
    explanation = (
        f"The AI water assessment model predicts that the water quality for this sample is <b>{status_label}</b>. "
        f"The calculated Water Quality Index (WQI) is <b>{p_wqi}</b>, which classifies the sample under the <b>'{p_wqi_cat}'</b> category. "
    )
    if is_safe:
        explanation += "Water with this score is generally suitable for drinking, irrigation, and household use without immediate restriction."
    else:
        explanation += "WARNING: Water contains high levels of target parameters. Boiling or multi-stage filtration purification is strongly recommended."
        
    result_para = Paragraph(f"{status_text}<br/>{explanation}", alert_style)
    result_table = Table([[result_para]], colWidths=[504])
    result_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('BOX', (0,0), (-1,-1), 1, border_color),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    story.append(Paragraph("AI Diagnostics & Report Findings", section_title_style))
    story.append(result_table)
    story.append(Spacer(1, 12))
    
    param_headers = [
        Paragraph("<b>Parameter</b>", body_style),
        Paragraph("<b>Measured Value</b>", body_style),
        Paragraph("<b>Unit</b>", body_style),
        Paragraph("<b>Status</b>", body_style)
    ]
    param_table_rows = [param_headers]
    
    params_list = [
        ('Temperature', prediction['temperature'], '°C'),
        ('Dissolved Oxygen', prediction['dissolved_oxygen'], 'mg/L'),
        ('pH', prediction['ph'], '-'),
        ('BOD', prediction['bod'], 'mg/L'),
    ]
    if prediction.get('faecal_streptococci') is not None:
        params_list.append(('Faecal Streptococci', prediction['faecal_streptococci'], 'CFU/100mL'))
        
    params_list.extend([
        ('Nitrate', prediction['nitrate'], 'mg/L'),
        ('Faecal Coliform', prediction['faecal_coliform'], 'CFU/100mL'),
        ('Total Coliform', prediction['total_coliform'], 'CFU/100mL'),
        ('Conductivity', prediction['conductivity'], 'μS/cm')
    ])
    
    for label, val, unit in params_list:
        if val is not None:
            status = check_parameter_status(label, val)
            status_color = '#0d9488' if status == 'Optimal' else '#ef4444'
            status_para = Paragraph(f"<font color='{status_color}'><b>{status}</b></font>", body_bold)
            
            if label in ['pH', 'Dissolved Oxygen', 'BOD', 'Nitrate']:
                val_str = f"{val:.2f}"
            else:
                val_str = f"{val:.1f}"
                
            param_table_rows.append([
                Paragraph(label, body_style),
                Paragraph(val_str, body_style),
                Paragraph(unit, body_style),
                status_para
            ])
            
    param_table = Table(param_table_rows, colWidths=[160, 110, 110, 124])
    param_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBELOW', (0,0), (-1,0), 1.5, colors.HexColor('#0369a1')),
        ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    
    for col_idx in range(4):
        param_table_rows[0][col_idx].style.textColor = colors.white
        param_table_rows[0][col_idx].style.alignment = 1
        
    story.append(Paragraph("Water Quality Parameters", section_title_style))
    story.append(param_table)
    story.append(Spacer(1, 10))
    
    try:
        custom_params = json.loads(prediction.get('custom_parameters') or '[]')
    except Exception:
        custom_params = []
        
    if custom_params:
        add_rows = [[
            Paragraph("<b>Parameter</b>", body_style),
            Paragraph("<b>Measured Value</b>", body_style),
            Paragraph("<b>Unit</b>", body_style),
            Paragraph("<b>Status</b>", body_style)
        ]]
        for col_idx in range(4):
            add_rows[0][col_idx].style.textColor = colors.white
            add_rows[0][col_idx].style.alignment = 1
            
        for cp in custom_params:
            add_rows.append([
                Paragraph(cp.get('name', 'N/A'), body_style),
                Paragraph(str(cp.get('value', 'N/A')), body_style),
                Paragraph(cp.get('unit', '-'), body_style),
                Paragraph("<font color='#64748b'><b>Entered</b></font>", body_bold)
            ])
            
        add_table = Table(add_rows, colWidths=[160, 110, 110, 124])
        add_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#5c646b')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LINEBELOW', (0,0), (-1,0), 1.5, colors.HexColor('#4c545b')),
            ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        story.append(Paragraph("Additional Parameters", section_title_style))
        story.append(add_table)
        story.append(Spacer(1, 10))

    story.append(PageBreak())
    
    # --- PAGE 2: CHARTS & METICS ---
    pie_drawing = draw_pie_chart(safe_preds, unsafe_preds)
    
    user_wqi_history = []
    for p in reversed(all_user_preds[:10]):
        if all(p.get(k) is not None for k in ['dissolved_oxygen', 'ph', 'bod', 'nitrate', 'conductivity']):
            w_val, _ = calculate_wqi(p['dissolved_oxygen'], p['ph'], p['bod'], p['nitrate'], p['conductivity'])
            user_wqi_history.append(w_val)
            
    trend_drawing = draw_wqi_trend_chart(user_wqi_history)
    
    charts_row = Table([[pie_drawing, trend_drawing]], colWidths=[240, 264])
    charts_row.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    
    story.append(Paragraph("Diagnostics Distribution & Trend Line", section_title_style))
    story.append(charts_row)
    story.append(Spacer(1, 10))
    
    monthly_counts = [0] * 12
    for p in all_user_preds:
        created_val = p.get('created_at')
        if created_val:
            m = created_val.month
            monthly_counts[m - 1] += 1
            
    bar_drawing = draw_bar_chart(monthly_counts)
    story.append(Paragraph("Prediction Activity (Monthly)", section_title_style))
    story.append(bar_drawing)
    story.append(Spacer(1, 10))
    
    detail_blocks = []
    
    if field_inspection:
        insp_items = [
            f"<b>Appearance:</b> {field_inspection.get('water_appearance') or 'N/A'} | "
            f"<b>Colour:</b> {field_inspection.get('water_colour') or 'N/A'} | "
            f"<b>Odour:</b> {field_inspection.get('water_odour') or 'N/A'}"
        ]
        if field_inspection.get('inspector_remarks'):
            insp_items.append(f"<b>Observation Notes:</b> {field_inspection.get('inspector_remarks')}")
        if field_inspection.get('recommended_action'):
            insp_items.append(f"<b>Precaution Methods:</b> {field_inspection.get('recommended_action')}")
        if field_inspection.get('sample_sent_to_lab') == 'Yes' or field_inspection.get('laboratory_name'):
            insp_items.append(
                f"<b>Laboratory Name:</b> {field_inspection.get('laboratory_name') or 'N/A'} | "
                f"<b>Reference:</b> {field_inspection.get('laboratory_ref') or 'N/A'} | "
                f"<b>Sample ID:</b> {field_inspection.get('sample_id') or 'N/A'}"
            )
            
        block_text = "<br/>".join(insp_items)
        insp_block = [
            Paragraph("<b>PHYSICAL FIELD INSPECTION</b>", body_bold),
            Spacer(1, 4),
            Paragraph(block_text, body_style)
        ]
        detail_blocks.append(insp_block)
        
    model_rows_text = (
        f"<b>Model Name:</b> Random Forest Classifier<br/>"
        f"<b>Model Type:</b> Supervised Learning (Classification)<br/>"
        f"<b>Accuracy:</b> {model_accuracy}%<br/>"
        f"<b>Training Data:</b> 1000 samples<br/>"
        f"<b>Testing Data:</b> 500 samples"
    )
    model_block = [
        Paragraph("<b>ML MODEL CONFIGURATION</b>", body_bold),
        Spacer(1, 4),
        Paragraph(model_rows_text, body_style)
    ]
    detail_blocks.append(model_block)
    
    if len(detail_blocks) == 2:
        details_table = Table([[detail_blocks[0], detail_blocks[1]]], colWidths=[246, 258])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
    else:
        details_table = Table([[detail_blocks[0]]], colWidths=[504])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        
    story.append(Paragraph("Official Diagnoses & Meta Configuration Info", section_title_style))
    story.append(details_table)
    
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer

@app.route('/download_report/<int:prediction_id>')
@login_required
def download_report(prediction_id):
    user_id = session.get("user_id")
    role = session.get("role")
    
    if not user_id:
        flash("Please log in to download reports.", "danger")
        return redirect(url_for('login'))
        
    try:
        cursor = get_db_cursor()
        
        cursor.execute("SELECT * FROM predictions WHERE id = %s", (prediction_id,))
        prediction = cursor.fetchone()
        
        if not prediction:
            flash("Report not found.", "danger")
            return redirect(url_for('dashboard') if role == 'user' else 'admin_dashboard')
            
        if role not in ['admin', 'inspector'] and prediction['user_id'] != user_id: # type: ignore
            flash("Unauthorized access.", "danger")
            return redirect(url_for('dashboard'))
            
        cursor.execute("SELECT name, email FROM users WHERE id = %s", (prediction['user_id'],)) # type: ignore
        user_record = cursor.fetchone()
        
        cursor.execute("SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (prediction['user_id'],)) # type: ignore
        all_user_preds = cursor.fetchall()
        
        cursor.execute("""
            SELECT fi.*, i.full_name as inspector_name
            FROM field_inspections fi
            LEFT JOIN inspectors i ON fi.inspector_id = i.inspector_id
            WHERE fi.appointment_id = (
                SELECT appointment_id FROM appointments WHERE prediction_id = %s LIMIT 1
            )
            LIMIT 1
        """, (prediction_id,))
        field_inspection = cursor.fetchone()
        
        model_metrics = get_model_metrics()
        
        pdf_buffer = generate_pdf_report_buffer(
            prediction,
            user_record,
            all_user_preds,
            field_inspection,
            model_metrics
        )
        
        return Response(
            pdf_buffer.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Aquaguard_Report_{prediction_id}.pdf"}
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Error generating PDF report: {e}", "danger")
        return redirect(url_for('dashboard') if role == 'user' else 'admin_dashboard')

@app.route('/inspector/precautions')
@login_required
def inspector_precautions():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    return render_template('inspector_precautions.html')

@app.route('/inspector/field-inspection', methods=['GET', 'POST'])
@login_required
def inspector_field_inspection():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    
    if request.method == 'POST':
        user_id = request.form.get("user_id") or None
        appointment_id = request.form.get("appointment_id") or None
        temperature = request.form.get("temperature")
        ph = request.form.get("ph")
        do = request.form.get("dissolved_oxygen")
        bod = request.form.get("bod")
        cond = request.form.get("conductivity")
        nitrate = request.form.get("nitrate")
        faecal_strep = request.form.get("faecal_streptococci")
        faecal_coli = request.form.get("faecal_coliform")
        total_coli = request.form.get("total_coliform")
        
        insp_date = request.form.get("inspection_date")
        insp_time = request.form.get("inspection_time")
        water_src = request.form.get("water_source")
        water_app = request.form.get("water_appearance")
        water_col = request.form.get("water_colour")
        water_odour = request.form.get("water_odour")
        vis_cont = request.form.get("visible_contamination")
        near_poll = request.form.get("nearby_pollution")
        drain_leak = request.form.get("drainage_leakage")
        samp_coll = request.form.get("sample_collected")
        rem = request.form.get("inspector_remarks")
        assess = request.form.get("inspector_assessment")
        pdf_path = request.form.get("pdf_path") or None
 
        # New fields
        sample_id = request.form.get("sample_id")
        sample_collection_time = request.form.get("sample_collection_time") or None
        sample_type = request.form.get("sample_type")
        sample_count = request.form.get("sample_count") or None
        container_type = request.form.get("container_type")
        preservation_method = request.form.get("preservation_method")
        sample_sent_to_lab = request.form.get("sample_sent_to_lab")
        laboratory_name = request.form.get("laboratory_name")
        laboratory_ref = request.form.get("laboratory_ref")
        inspection_summary = request.form.get("inspection_summary")
        recommended_action = request.form.get("recommended_action")
 
        if appointment_id:
            cursor.execute("SELECT inspection_type, status, user_id FROM appointments WHERE appointment_id = %s", (appointment_id,))
            apt_chk = cursor.fetchone()
            if apt_chk:
                if apt_chk['inspection_type'] == 'Online Inspection':
                    flash("Field Inspection is not available for this Online-Only inspection.", "warning")
                    return redirect(url_for('inspector_dashboard'))
                if apt_chk.get('user_id'):
                    user_id = apt_chk['user_id']
 
        # Validation of required fields
        if not all([insp_date, insp_time, water_src, water_app, water_col, water_odour, vis_cont, near_poll, drain_leak, samp_coll, assess]):
            flash("Please complete all required fields before submitting the inspection.", "danger")
            return redirect(url_for('inspector_field_inspection', appointment_id=appointment_id))

        # Range and numerical type validation
        try:
            if temperature and str(temperature).strip():
                t_val = float(temperature)
                if t_val < -50 or t_val > 100:
                    flash("Temperature is out of valid scientific range (-50 to 100).", "danger")
                    return redirect(url_for('inspector_field_inspection', appointment_id=appointment_id))
            if ph and str(ph).strip():
                ph_val = float(ph)
                if not (0 <= ph_val <= 14):
                    flash("pH must be between 0 and 14.", "danger")
                    return redirect(url_for('inspector_field_inspection', appointment_id=appointment_id))
            for val, name in [
                (do, "Dissolved Oxygen"),
                (bod, "BOD"),
                (cond, "Conductivity"),
                (nitrate, "Nitrate"),
                (faecal_strep, "Faecal Streptococci"),
                (faecal_coli, "Faecal Coliform"),
                (total_coli, "Total Coliform")
            ]:
                if val and str(val).strip():
                    v_val = float(val)
                    if v_val < 0:
                        flash(f"{name} cannot be negative.", "danger")
                        return redirect(url_for('inspector_field_inspection', appointment_id=appointment_id))
        except ValueError:
            flash("Please enter a valid numeric value.", "danger")
            return redirect(url_for('inspector_field_inspection', appointment_id=appointment_id))

        try:
            cursor.execute('''
                INSERT INTO field_inspections (
                    inspector_id, user_id, appointment_id, temperature, ph, dissolved_oxygen, bod,
                    conductivity, nitrate, faecal_streptococci, faecal_coliform, total_coliform,
                    inspection_date, inspection_time, water_source, water_appearance, water_colour,
                    water_odour, visible_contamination, nearby_pollution, drainage_leakage, sample_collected,
                    inspector_remarks, inspector_assessment, pdf_path,
                    sample_id, sample_collection_time, sample_type, sample_count, container_type,
                    preservation_method, sample_sent_to_lab, laboratory_name, laboratory_ref,
                    inspection_summary, recommended_action
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (session["user_id"], user_id, appointment_id, temperature, ph, do, bod, cond, nitrate, faecal_strep, faecal_coli, total_coli, insp_date, insp_time, water_src, water_app, water_col, water_odour, vis_cont, near_poll, drain_leak, samp_coll, rem, assess, pdf_path,
                  sample_id, sample_collection_time, sample_type, sample_count, container_type, preservation_method, sample_sent_to_lab, laboratory_name, laboratory_ref, inspection_summary, recommended_action))
            inspection_id = cursor.lastrowid
 
            # Save Photos
            upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'inspections')
            os.makedirs(upload_folder, exist_ok=True)
            for photo_key in ['photo_sample', 'photo_source', 'photo_surrounding', 'photo_pollution', 'photo_equipment', 'photo_additional']:
                if photo_key in request.files:
                    files = request.files.getlist(photo_key)
                    for file in files:
                        if file and file.filename != '':
                            filename = secure_filename(f"{inspection_id}_{photo_key}_{file.filename}")
                            file_path = os.path.join(upload_folder, filename)
                            file.save(file_path)
                            desc = request.form.get(f"{photo_key}_desc", "")
                            cursor.execute("INSERT INTO field_inspection_photos (inspection_id, photo_type, file_path, description) VALUES (%s, %s, %s, %s)", (inspection_id, photo_key, f"/static/uploads/inspections/{filename}", desc))
 
            # Save Techniques
            techniques_json = request.form.get("techniques_data")
            if techniques_json:
                techniques = json.loads(techniques_json)
                for tech in techniques:
                    cursor.execute("""
                        INSERT INTO field_inspection_techniques (
                            inspection_id, technique, notes, equipment_name, equipment_model,
                            instrument_id, calibration_status, calibration_date, measurement_unit, remarks
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (inspection_id, tech.get('technique'), tech.get('notes'), tech.get('equipment_name'), tech.get('equipment_model'), tech.get('instrument_id'), tech.get('calibration_status'), tech.get('calibration_date') or None, tech.get('measurement_unit'), tech.get('remarks')))
 
            # Save Measurements
            measurements_json = request.form.get("measurements_data")
            if measurements_json:
                measurements = json.loads(measurements_json)
                for meas in measurements:
                    cursor.execute("""
                        INSERT INTO field_inspection_measurements (
                            inspection_id, parameter, value, unit, technique, instrument, measurement_time, remarks
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (inspection_id, meas.get('parameter'), meas.get('value') or None, meas.get('unit'), meas.get('technique'), meas.get('instrument'), meas.get('time') or None, meas.get('remarks')))
 
            if appointment_id:
                cursor.execute("UPDATE appointments SET field_status='Completed' WHERE appointment_id=%s", (appointment_id,))
                db.commit()
                finalize_appointment_report(appointment_id, session['user_id'])
                flash("Field Inspection saved and sub-status updated successfully.", "success")
                return redirect(url_for('inspector_dashboard'))
            else:
                db.commit()
                flash("Field Inspection saved successfully.", "success")
                return redirect(url_for('inspector_history'))
        except Exception as e:
            flash(f"Error saving inspection: {e}", "danger")
            db.rollback()
    
    # GET request
    appointment_id = request.args.get("appointment_id")
    selected_user_id = None
    appointment_details = None
    if appointment_id:
        cursor.execute("""
            SELECT a.*, u.name as user_name, u.email, u.phone_number
            FROM appointments a 
            LEFT JOIN users u ON a.user_id = u.id 
            WHERE a.appointment_id = %s
        """, (appointment_id,))
        apt_row = cursor.fetchone()
        if apt_row:
            if apt_row['status'] in ('Pending Inspector Approval', 'Pending') or apt_row.get('assignment_status') == 'Pending Inspector Approval':
                flash("You must approve the inspection assignment before starting field inspection.", "danger")
                return redirect(url_for('inspector_dashboard'))
            if apt_row['inspection_type'] == 'Online Inspection':
                flash("Field Inspection is not available for this Online-Only appointment.", "warning")
                return redirect(url_for('inspector_dashboard'))
            selected_user_id = apt_row['user_id']
            appointment_details = make_json_serializable(apt_row)
            
    cursor.execute("SELECT id, name, email, phone_number FROM users WHERE role='user'")
    users = cursor.fetchall()
    
    now = datetime.now()
    return render_template('field_inspection.html', users=users, today=now.strftime("%Y-%m-%d"), time_now=now.strftime("%H:%M"), appointment_id=appointment_id, selected_user_id=selected_user_id, appointment_details=appointment_details)

@app.route('/inspector/profile', methods=['GET', 'POST'])
@login_required
def inspector_profile():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    insp_id = session.get("user_id")
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            fn = request.form.get('full_name', '').strip()
            ph = request.form.get('phone', '').strip()
            if not fn or not ph:
                flash("Please fill in all required fields before submitting.", "danger")
            elif not is_valid_name(fn):
                flash("Name must contain letters and spaces only.", "danger")
            elif not is_valid_phone(ph):
                flash("Phone number must contain exactly 10 digits.", "danger")
            else:
                try:
                    cursor.execute("UPDATE inspectors SET full_name=%s, phone=%s WHERE inspector_id=%s", (fn, ph, insp_id))
                    db.commit()
                    session['name'] = fn
                    flash("Profile updated successfully.", "success")
                except Exception as e:
                    flash("Error updating profile.", "danger")
        elif action == 'change_password':
            curr = request.form.get('current_password')
            new_p = request.form.get('new_password')
            conf = request.form.get('confirm_password')
            
            if not new_p or not conf or not curr:
                flash("Please fill in all required fields before submitting.", "danger")
            elif not is_valid_password(new_p):
                flash("Password must contain at least one letter and one number.", "danger")
            elif new_p != conf:
                flash("Password and Confirm Password do not match.", "danger")
            else:
                cursor.execute("SELECT password FROM inspectors WHERE inspector_id=%s", (insp_id,))
                res = cursor.fetchone()
                if not res or not check_password_hash(res['password'], curr):
                    flash("Incorrect current password.", "danger")
                else:
                    cursor.execute("UPDATE inspectors SET password=%s WHERE inspector_id=%s", (generate_password_hash(new_p), insp_id))
                    db.commit()
                    flash("Password changed successfully.", "success")
                
    cursor.execute("SELECT * FROM inspectors WHERE inspector_id=%s", (insp_id,))
    inspector = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE inspector_id=%s", (insp_id,))
    assigned = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE inspector_id=%s AND status='Completed'", (insp_id,))
    completed = cursor.fetchone()['c']
    
    return render_template('inspector_profile.html', inspector=inspector, stats={'assigned': assigned, 'completed': completed})

@app.route('/inspector/history')
@login_required
def inspector_history():
    if session.get("role") != "inspector": return redirect(url_for("login"))
    
    cursor.execute('''
        SELECT f.*, u.name as user_name, p.prediction as ai_prediction
        FROM field_inspections f
        LEFT JOIN users u ON f.user_id = u.id
        LEFT JOIN appointments a ON f.appointment_id = a.appointment_id
        LEFT JOIN predictions p ON a.prediction_id = p.id
        WHERE f.inspector_id = %s
        ORDER BY f.created_at DESC
    ''', (session["user_id"],))
    inspections = cursor.fetchall()
    
    return render_template('inspector_history.html', inspections=inspections)

if __name__ == "__main__":
    app.run(debug=True)
