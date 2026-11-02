import sys
import re

with open("app.py", "r") as f:
    content = f.read()

if "import json\n" not in content[:500]:
    content = content.replace("import os", "import os\nimport json", 1)

# Modify predict route to extract custom params
old_extract = """            cond = float(request.form.get("conductivity", 0))"""
new_extract = """            cond = float(request.form.get("conductivity", 0))
            
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
            custom_params_json = json.dumps(custom_params) if custom_params else None"""

content = content.replace(old_extract, new_extract)

# Modify prediction_data dict
old_pred_data = """                "recommendation": rec,
                "timestamp": datetime.now()"""
new_pred_data = """                "recommendation": rec,
                "timestamp": datetime.now(),
                "custom_parameters": custom_params
"""
content = content.replace(old_pred_data, new_pred_data)

# Modify INSERT query
old_insert_sql = """                    INSERT INTO predictions 
                    (user_id, water_source, temperature, dissolved_oxygen, ph, bod, 
                     nitrate, faecal_coliform, total_coliform, conductivity, 
                     prediction, pollution_level, recommendation, prediction_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

new_insert_sql = """                    INSERT INTO predictions 
                    (user_id, water_source, temperature, dissolved_oxygen, ph, bod, 
                     nitrate, faecal_coliform, total_coliform, conductivity, 
                     prediction, pollution_level, recommendation, prediction_source, custom_parameters)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

content = content.replace(old_insert_sql, new_insert_sql)

old_insert_val = """                        pollution,
                        rec,
                        prediction_source
                    )"""

new_insert_val = """                        pollution,
                        rec,
                        prediction_source,
                        custom_params_json
                    )"""
content = content.replace(old_insert_val, new_insert_val)

with open("app.py", "w") as f:
    f.write(content)
print("app.py updated!")
