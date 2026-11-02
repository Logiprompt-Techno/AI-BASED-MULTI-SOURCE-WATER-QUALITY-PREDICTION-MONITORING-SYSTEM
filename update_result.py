import sys

with open("templates/result.html", "r", encoding="utf-8") as f:
    content = f.read()

custom_params_html = """
        {% set custom_params = data.custom_parameters|fromjson %}
        {% if custom_params %}
        <div class="detail-item" style="flex-direction: column; align-items: flex-start;">
            <span style="color: var(--text-secondary); margin-bottom: 0.5rem; font-weight: bold;">Additional Parameters</span>
            <table style="width: 100%; border-collapse: collapse; margin-top: 0.5rem; background: rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background: rgba(255,255,255,0.05);">
                        <th style="padding: 0.5rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1);">Parameter</th>
                        <th style="padding: 0.5rem; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.1);">Value</th>
                        <th style="padding: 0.5rem; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.1);">Unit</th>
                    </tr>
                </thead>
                <tbody>
                    {% for param in custom_params %}
                    <tr>
                        <td style="padding: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.05);">{{ param.name }}</td>
                        <td style="padding: 0.5rem; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.05); font-weight: 500;">{{ param.value }}</td>
                        <td style="padding: 0.5rem; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.05); color: var(--text-secondary);">{{ param.unit }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
"""

# Insert before the last </div> in result-details
target = """        <div class="detail-item">
            <span style="color: var(--text-secondary);">Recommendation</span>
            <span style="font-weight: 500; text-align: right; max-width: 60%;">{{ data.recommendation }}</span>
        </div>"""

replacement = target + "\n" + custom_params_html

if custom_params_html not in content:
    content = content.replace(target, replacement)
    with open("templates/result.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("result.html updated!")
else:
    print("already updated.")
