import re
import glob

for filepath in glob.glob('templates/*.html'):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace `.id` with `.get('id')` when preceded by typical variables like data, item, prediction
    new_content = re.sub(r'(data|item|prediction)\.id\b', r"\1.get('id')", content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")
