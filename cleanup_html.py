import re

# Clean up base.html
with open('templates/base.html', 'r', encoding='utf-8') as f:
    base_html = f.read()

# Remove the Reports link
base_html = re.sub(r'\s*<li><a href="{{ url_for\(\'admin_reports\'\).*?</li>', '', base_html)

with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(base_html)


# Clean up admin_dashboard.html
with open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    admin_dash = f.read()

# Remove buttons
admin_dash = re.sub(r'\s*<a href="{{ url_for\(\'admin_reports\'\).*?</a>', '', admin_dash)
admin_dash = re.sub(r'\s*<a href="{{ url_for\(\'admin_payments\'\).*?</a>', '', admin_dash)

# Remove Total Revenue stat block
admin_dash = re.sub(r'\s*<div class="glass-card stat-card".*?Total Revenue.*?</div>\s*</div>', '\n</div>', admin_dash, flags=re.DOTALL)

# Remove "View All" link to admin_reports in Recent Predictions
admin_dash = re.sub(r'<a href="{{ url_for\(\'admin_reports\'\)".*?</a>', '', admin_dash)

with open('templates/admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(admin_dash)

print("HTML cleanup complete.")
