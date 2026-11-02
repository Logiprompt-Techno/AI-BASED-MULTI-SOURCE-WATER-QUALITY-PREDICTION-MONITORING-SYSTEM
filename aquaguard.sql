CREATE DATABASE IF NOT EXISTS aquaguard;
USE aquaguard;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    mobile VARCHAR(20) DEFAULT NULL,
    phone_number VARCHAR(20) UNIQUE,
    profile_image VARCHAR(255) DEFAULT 'default.png',
    role VARCHAR(50) DEFAULT 'user',
    status VARCHAR(50) DEFAULT 'active',
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    water_source VARCHAR(100) NOT NULL,
    temperature FLOAT NOT NULL,
    dissolved_oxygen FLOAT NOT NULL,
    ph FLOAT NOT NULL,
    bod FLOAT NOT NULL,
    nitrate FLOAT NOT NULL,
    faecal_coliform FLOAT NOT NULL,
    total_coliform FLOAT NOT NULL,
    conductivity FLOAT NOT NULL,
    prediction VARCHAR(50) NOT NULL,
    pollution_level VARCHAR(100) NOT NULL,
    recommendation TEXT NOT NULL,
    prediction_source VARCHAR(50) DEFAULT 'Manual Entry',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);





CREATE TABLE IF NOT EXISTS inspectors (
    inspector_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL,
    password VARCHAR(255) NOT NULL,
    district VARCHAR(100) NOT NULL,
    designation VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    prediction_id INT NOT NULL,
    inspector_id INT DEFAULT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    address TEXT NOT NULL,
    issue_description TEXT,
    status VARCHAR(50) DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id) ON DELETE CASCADE,
    FOREIGN KEY (inspector_id) REFERENCES inspectors(inspector_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS inspection_reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    inspector_id INT NOT NULL,
    findings TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    inspection_date DATE NOT NULL,
    report_file VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    FOREIGN KEY (inspector_id) REFERENCES inspectors(inspector_id) ON DELETE CASCADE
);
