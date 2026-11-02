import sys

with open("app.py", "r") as f:
    content = f.read()

filter_code = """
@app.template_filter('fromjson')
def fromjson_filter(s):
    try:
        import json
        return json.loads(s) if s else []
    except:
        return []
"""

if "fromjson_filter" not in content:
    content = content.replace("csrf = CSRFProtect(app)", "csrf = CSRFProtect(app)\n" + filter_code)
    
with open("app.py", "w") as f:
    f.write(content)
print("Filter added!")
