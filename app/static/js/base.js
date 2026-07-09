(() => {
    const storageKey = "nexora-theme";
    const body = document.body;
    const toggleButton = document.querySelector("#theme-toggle");

    if (!toggleButton) {
        return;
    }

    const readSavedTheme = () => {
        try {
            return localStorage.getItem(storageKey);
        } catch {
            return null;
        }
    };

    const saveTheme = (theme) => {
        try {
            localStorage.setItem(storageKey, theme);
        } catch {
            // The theme still changes when storage is unavailable.
        }
    };

    const applyTheme = (theme) => {
        const isDark = theme === "dark";

        body.classList.toggle("theme-dark", isDark);
        body.classList.toggle("theme-light", !isDark);
        body.dataset.theme = theme;

        toggleButton.setAttribute("aria-pressed", String(isDark));
    };

    const currentTheme = () => body.classList.contains("theme-dark") ? "dark" : "light";
    const savedTheme = readSavedTheme();

    applyTheme(savedTheme === "dark" ? "dark" : "light");

    toggleButton.addEventListener("click", () => {
        const nextTheme = currentTheme() === "dark" ? "light" : "dark";

        applyTheme(nextTheme);
        saveTheme(nextTheme);
    });
})();
