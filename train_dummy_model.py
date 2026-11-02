import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
import pickle
import os

# Create dummy data for training
np.random.seed(42)
n_samples = 1000

# Features: Temperature, DO, pH, BOD, Faecal_Streptococci, Nitrate, Faecal_Coliform, Total_Coliform, Conductivity
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

# Add some missing values
X.loc[np.random.choice(X.index, 50), 'DO'] = np.nan
X.loc[np.random.choice(X.index, 30), 'pH'] = np.nan

# Simple dummy logic for labels (1 = SAFE, 0 = UNSAFE)
# Safe if DO > 5, pH between 6.5 and 8.5, BOD < 5
safe_condition = (X['DO'] > 4) & (X['pH'] >= 6.0) & (X['pH'] <= 9.0) & (X['BOD'] < 10)
y = np.where(safe_condition, 1, 0)

# Train Imputer
imputer = SimpleImputer(strategy='median')
X_imputed = imputer.fit_transform(X)

# Train Model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_imputed, y)

# Save models
with open('wqi_imputer.pkl', 'wb') as f:
    pickle.dump(imputer, f)

with open('wqi_model.pkl', 'wb') as f:
    pickle.dump(model, f)

print("Dummy models wqi_model.pkl and wqi_imputer.pkl created successfully.")
