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
        toggleButton.setAttribute(
            "aria-label",
            isDark ? toggleButton.dataset.lightLabel : toggleButton.dataset.darkLabel,
        );
    };

    const currentTheme = () => body.classList.contains("theme-dark") ? "dark" : "light";
    const savedTheme = readSavedTheme();
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    applyTheme(savedTheme === "dark" || (savedTheme !== "light" && systemPrefersDark) ? "dark" : "light");

    toggleButton.addEventListener("click", () => {
        const nextTheme = currentTheme() === "dark" ? "light" : "dark";

        applyTheme(nextTheme);
        saveTheme(nextTheme);
    });
})();

(() => {
    const header = document.querySelector("header");
    const menuButton = document.querySelector("#mobile-menu-toggle");
    const menu = document.querySelector("#header-menu");

    if (!header || !menuButton || !menu) {
        return;
    }

    const mobileQuery = window.matchMedia("(max-width: 1280px)");
    const firstMenuLink = menu.querySelector("a");

    const setMenuOpen = (isOpen, moveFocus = false) => {
        const canOpen = mobileQuery.matches;
        const nextOpen = canOpen && isOpen;

        header.classList.toggle("is-menu-open", nextOpen);
        menuButton.setAttribute("aria-expanded", String(nextOpen));
        menuButton.setAttribute(
            "aria-label",
            nextOpen ? menuButton.dataset.closeLabel : menuButton.dataset.openLabel,
        );
        menu.hidden = canOpen && !nextOpen;

        if (nextOpen && moveFocus) {
            firstMenuLink?.focus();
        }
    };

    header.classList.add("has-mobile-menu");

    menuButton.addEventListener("click", () => {
        setMenuOpen(!header.classList.contains("is-menu-open"), true);
    });

    menu.addEventListener("click", (event) => {
        if (event.target.closest("a")) {
            setMenuOpen(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && header.classList.contains("is-menu-open")) {
            setMenuOpen(false);
            menuButton.focus();
        }
    });

    document.addEventListener("click", (event) => {
        if (
            header.classList.contains("is-menu-open")
            && !header.contains(event.target)
        ) {
            setMenuOpen(false);
        }
    });

    mobileQuery.addEventListener("change", () => {
        setMenuOpen(false);
    });

    setMenuOpen(false);
})();

(() => {
    const errorSummary = document.querySelector("[data-error-summary]");

    if (errorSummary) {
        const focusSummary = () => window.setTimeout(() => errorSummary.focus(), 0);

        if (document.readyState === "complete") {
            focusSummary();
        } else {
            window.addEventListener("load", focusSummary, {once: true});
        }
    }
})();
