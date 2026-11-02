import re

# 1. Update app.py
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()

# Remove imports
app_content = re.sub(r'import razorpay\n', '', app_content)
app_content = re.sub(r'from reportlab.*?\n', '', app_content)

# Remove razorpay config
app_content = re.sub(r'# Razorpay config\nRAZORPAY_KEY_ID = os\.getenv\(\'RAZORPAY_KEY_ID\', \'test\'\)\nRAZORPAY_KEY_SECRET = os\.getenv\(\'RAZORPAY_KEY_SECRET\', \'test\'\)\nrazorpay_client = razorpay\.Client\(auth=\(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET\)\)\n', '', app_content)

# Remove table creations
app_content = re.sub(r'\s*cursor\.execute\("""\s*CREATE TABLE IF NOT EXISTS payments.*?FOREIGN KEY \(user_id\) REFERENCES users\(id\) ON DELETE CASCADE\s*\)\s*"""\)\s*', '\n    ', app_content, flags=re.DOTALL)
app_content = re.sub(r'\s*cursor\.execute\("""\s*CREATE TABLE IF NOT EXISTS reports.*?FOREIGN KEY \(payment_id\) REFERENCES payments\(id\) ON DELETE CASCADE\s*\)\s*"""\)\s*', '\n    ', app_content, flags=re.DOTALL)

# Remove routes
app_content = re.sub(r'@app\.route\(\'/create_report_payment.*?(?=@app\.route\("/dashboard"\))', '', app_content, flags=re.DOTALL)
app_content = re.sub(r'@app\.route\("/admin/payments"\).*?(?=@app\.route\("/profile", methods=\["GET", "POST"\]\))', '', app_content, flags=re.DOTALL)

# Remove revenue from admin dashboard
app_content = re.sub(r'\s*cursor\.execute\("SELECT SUM\(amount\) as total_revenue FROM payments WHERE status = \'paid\'"\)\s*rev_row = cursor\.fetchone\(\)\s*total_revenue = \(rev_row\[\'total_revenue\'\] / 100\) if rev_row and rev_row\[\'total_revenue\'\] else 0\s*', '\n        ', app_content)
app_content = re.sub(r'"total_revenue": total_revenue,', '', app_content)

# In /history route, remove report_map logic
app_content = re.sub(r'\s*# Fetch user reports\s*cursor\.execute\("SELECT prediction_id, id as report_id FROM reports WHERE user_id = %s", \(user_id,\)\)\s*report_rows = cursor\.fetchall\(\)\s*report_map = \{row\[\'prediction_id\'\]: row\[\'report_id\'\] for row in report_rows\}\s*', '\n        ', app_content)
app_content = re.sub(r'"report_id": report_map\.get\(p\["id"\]\)', '', app_content)
app_content = re.sub(r',\s*}', '\n            }', app_content) # fix trailing comma if left

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(app_content)


# 2. Update aquaguard.sql
with open('aquaguard.sql', 'r', encoding='utf-8') as f:
    sql_content = f.read()

sql_content = re.sub(r'CREATE TABLE IF NOT EXISTS payments.*?;', '', sql_content, flags=re.DOTALL)
sql_content = re.sub(r'CREATE TABLE IF NOT EXISTS reports.*?;', '', sql_content, flags=re.DOTALL)

with open('aquaguard.sql', 'w', encoding='utf-8') as f:
    f.write(sql_content)


# 3. Update requirements.txt
with open('requirements.txt', 'r', encoding='utf-8') as f:
    req_content = f.read()

req_content = re.sub(r'razorpay\n?', '', req_content)
req_content = re.sub(r'reportlab\n?', '', req_content)

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(req_content)


# 4. Update templates/result.html
with open('templates/result.html', 'r', encoding='utf-8') as f:
    res_content = f.read()

res_content = re.sub(r'<button id="pay-btn".*?</button>', '', res_content)
res_content = re.sub(r'<script src="https://checkout\.razorpay\.com/v1/checkout\.js"></script>', '', res_content)
res_content = re.sub(r'document\.getElementById\(\'pay-btn\'\)\.onclick = function\(e\).*?(?=</script>)', '', res_content, flags=re.DOTALL)

with open('templates/result.html', 'w', encoding='utf-8') as f:
    f.write(res_content)


# 5. Update templates/history.html
with open('templates/history.html', 'r', encoding='utf-8') as f:
    hist_content = f.read()

hist_content = re.sub(r'{% if item\.report_id %}.*?{% endif %}', '', hist_content, flags=re.DOTALL)

with open('templates/history.html', 'w', encoding='utf-8') as f:
    f.write(hist_content)

print("Files modified.")
