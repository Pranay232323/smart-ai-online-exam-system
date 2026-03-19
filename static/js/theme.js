(function () {
    const root = document.documentElement;
    const storageKey = "exam_theme";

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        const toggle = document.getElementById("themeToggle");
        if (toggle) {
            toggle.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
        }
    }

    const savedTheme = localStorage.getItem(storageKey) || "light";
    applyTheme(savedTheme);

    window.toggleTheme = function () {
        const nextTheme =
            root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        localStorage.setItem(storageKey, nextTheme);
        applyTheme(nextTheme);
    };
})();
