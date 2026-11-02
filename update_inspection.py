import sys

with open("templates/inspection_details.html", "r", encoding="utf-8") as f:
    content = f.read()

custom_params_html = """                    {% set custom_params = details.custom_parameters|fromjson %}
                    {% if custom_params %}
                    {% for param in custom_params %}
                    <tr>
                        <td style="padding: 0.75rem 1rem;">{{ param.name }} {% if param.unit %}({{ param.unit }}){% endif %} <span style="font-size: 0.75em; color: var(--accent-primary);">(Custom)</span></td>
                        <td style="padding: 0.75rem 1rem;">{{ param.value }}</td>
                    </tr>
                    {% endfor %}
                    {% endif %}
                </tbody>"""

target = "                </tbody>"

if custom_params_html not in content:
    content = content.replace(target, custom_params_html)
    with open("templates/inspection_details.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("inspection_details.html updated!")
else:
    print("already updated.")
