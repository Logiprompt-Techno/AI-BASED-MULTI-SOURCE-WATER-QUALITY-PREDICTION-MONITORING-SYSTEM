document.addEventListener('DOMContentLoaded', () => {
    // Basic setup for validation on all forms
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', (e) => {
            let isValid = true;
            
            // Validate required fields
            const requiredFields = form.querySelectorAll('[required]');
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    showError(field, 'This field is required.');
                } else {
                    clearError(field);
                }
            });
            
            // Validate specific types
            const emails = form.querySelectorAll('input[type="email"]');
            emails.forEach(email => {
                if (email.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
                    isValid = false;
                    showError(email, 'Please enter a valid email address.');
                }
            });
            
            // Password strength if it has a pattern
            const passwords = form.querySelectorAll('input[type="password"][pattern]');
            passwords.forEach(pw => {
                const regex = new RegExp(pw.getAttribute('pattern'));
                if (pw.value && !regex.test(pw.value)) {
                    isValid = false;
                    showError(pw, pw.getAttribute('title') || 'Password does not meet requirements.');
                }
            });
            
            // Numeric ranges
            const numbers = form.querySelectorAll('input[type="number"]');
            numbers.forEach(num => {
                if (num.value !== '') {
                    const val = parseFloat(num.value);
                    const min = parseFloat(num.getAttribute('min'));
                    const max = parseFloat(num.getAttribute('max'));
                    
                    if (!isNaN(min) && val < min) {
                        isValid = false;
                        showError(num, `Value must be at least ${min}.`);
                    } else if (!isNaN(max) && val > max) {
                        isValid = false;
                        showError(num, `Value must be at most ${max}.`);
                    }
                }
            });
            
            if (!isValid) {
                e.preventDefault();
            }
        });
        
        // Add real-time validation feedback on blur/input
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                if (input.hasAttribute('required') && !input.value.trim()) {
                    showError(input, 'This field is required.');
                } else {
                    clearError(input);
                    // Trigger form validation to check patterns
                    if(input.checkValidity) {
                        if (!input.checkValidity()) {
                            showError(input, input.validationMessage || 'Invalid input.');
                        }
                    }
                }
            });
        });
    });
    
    function showError(input, message) {
        input.style.borderColor = 'var(--danger)';
        let errorSpan = input.nextElementSibling;
        if (!errorSpan || !errorSpan.classList.contains('validation-error')) {
            errorSpan = document.createElement('span');
            errorSpan.classList.add('validation-error');
            errorSpan.style.color = 'var(--danger)';
            errorSpan.style.fontSize = '0.8rem';
            errorSpan.style.display = 'block';
            errorSpan.style.marginTop = '0.25rem';
            input.parentNode.insertBefore(errorSpan, input.nextSibling);
        }
        errorSpan.textContent = message;
    }
    
    function clearError(input) {
        input.style.borderColor = 'var(--glass-border)';
        const errorSpan = input.nextElementSibling;
        if (errorSpan && errorSpan.classList.contains('validation-error')) {
            errorSpan.remove();
        }
    }
});
