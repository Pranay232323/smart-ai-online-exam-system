function togglePasswordVisibility(button) {
    const targetId = button.dataset.target;
    const input = document.getElementById(targetId);

    if (!input) {
        return;
    }

    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    button.textContent = isPassword ? "🙈" : "👁";
    button.setAttribute(
        "aria-label",
        isPassword ? "Hide password" : "Show password"
    );
}

window.togglePasswordVisibility = togglePasswordVisibility;
