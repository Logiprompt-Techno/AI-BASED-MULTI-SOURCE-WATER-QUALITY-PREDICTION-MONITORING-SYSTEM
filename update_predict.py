import sys

with open("templates/predict.html", "r") as f:
    content = f.read()

custom_params_html = """
        <hr style="border-color: rgba(255,255,255,0.1); margin: 3rem 0;">

        <div style="text-align: center; margin-bottom: 1.5rem;">
            <h3>Additional Parameters</h3>
            <p style="color: var(--text-secondary); font-size: 0.9rem;">Add any extra laboratory or observation values here (e.g. Turbidity, TDS).</p>
        </div>

        <div id="custom-parameters-container" style="max-width: 800px; margin: 0 auto;">
            <!-- Custom params will be appended here -->
        </div>

        <div style="text-align: center; margin-bottom: 2rem;">
            <button type="button" class="btn btn-outline" id="add-param-btn">
                <i class="fa-solid fa-plus"></i> Add Parameter
            </button>
        </div>
"""

custom_params_js = """
    // Dynamic Custom Parameters
    const addParamBtn = document.getElementById('add-param-btn');
    const customParamsContainer = document.getElementById('custom-parameters-container');
    let paramCount = 0;

    addParamBtn.addEventListener('click', () => {
        paramCount++;
        const row = document.createElement('div');
        row.className = 'custom-param-row';
        row.style.display = 'flex';
        row.style.gap = '1rem';
        row.style.marginBottom = '1rem';
        row.style.alignItems = 'center';
        row.innerHTML = `
            <input type="text" name="custom_name[]" class="form-control" placeholder="Parameter Name (e.g. Turbidity)" required style="flex: 2;">
            <input type="number" step="any" name="custom_value[]" class="form-control" placeholder="Value" required style="flex: 1;">
            <input type="text" name="custom_unit[]" class="form-control" placeholder="Unit (e.g. NTU)" style="flex: 1;">
            <button type="button" class="btn btn-danger remove-param-btn" style="padding: 0.5rem 1rem; border: none; background: #ff4757; color: white; border-radius: 0.5rem; cursor: pointer;">&times;</button>
        `;
        customParamsContainer.appendChild(row);

        row.querySelector('.remove-param-btn').addEventListener('click', () => {
            row.remove();
        });
    });
</script>
"""

content = content.replace(
    '<hr style="border-color: rgba(255,255,255,0.1); margin: 3rem 0;">',
    custom_params_html + '\n        <hr style="border-color: rgba(255,255,255,0.1); margin: 3rem 0;">',
    1
)

content = content.replace('</script>', custom_params_js)

with open("templates/predict.html", "w") as f:
    f.write(content)
print("predict.html updated!")
