(() => {
    const cards = document.querySelectorAll("[data-demo-card]");

    const textValue = (card, name, fallback) => {
        const value = card.querySelector(`[data-demo-field="${name}"]`)?.value.trim();
        return value || fallback;
    };

    const numberValue = (card, name, fallback) => {
        const value = Number(card.querySelector(`[data-demo-field="${name}"]`)?.value);
        return Number.isFinite(value) ? value : fallback;
    };

    const updateSpotify = (card) => {
        const preview = card.querySelector("[data-demo-preview]");
        const title = card.querySelector('[data-demo-output="title"]');
        const artist = card.querySelector('[data-demo-output="artist"]');
        const accent = card.querySelector('[data-demo-field="accent"]')?.value || "#1ed760";

        title.textContent = textValue(card, "title", "Midnight Drive");
        artist.textContent = textValue(card, "artist", "Nova Waves");
        preview.style.setProperty("--demo-accent", accent);
    };

    const updateWinChallenge = (card) => {
        const preview = card.querySelector("[data-demo-preview]");
        const winsInput = card.querySelector('[data-demo-field="wins"]');
        const target = Math.max(1, Math.min(999, Math.round(numberValue(card, "target", 10))));
        const wins = Math.max(0, Math.min(target, Math.round(numberValue(card, "wins", 0))));
        const accent = card.querySelector('[data-demo-field="accent"]')?.value || "#f59e0b";
        const progress = card.querySelector("[data-demo-progress]");
        const progressBar = progress.parentElement;

        card.querySelector('[data-demo-output="title"]').textContent = textValue(card, "title", "Road to Diamond");
        card.querySelector('[data-demo-output="game"]').textContent = textValue(card, "game", "Rocket League");
        card.querySelector('[data-demo-output="score"]').textContent = `${wins} / ${target}`;
        winsInput.max = String(target);
        progress.style.width = `${Math.round((wins / target) * 100)}%`;
        progressBar.setAttribute("aria-valuemax", String(target));
        progressBar.setAttribute("aria-valuenow", String(wins));
        preview.style.setProperty("--demo-accent", accent);
    };

    cards.forEach((card) => {
        const update = card.dataset.demoCard === "spotify" ? updateSpotify : updateWinChallenge;
        const preview = card.querySelector("[data-demo-preview]");

        card.addEventListener("input", () => update(card));

        card.querySelectorAll("[data-demo-style]").forEach((button) => {
            button.addEventListener("click", () => {
                preview.dataset.style = button.dataset.demoStyle;
                card.querySelectorAll("[data-demo-style]").forEach((styleButton) => {
                    styleButton.setAttribute("aria-pressed", String(styleButton === button));
                });
            });
        });

        update(card);
    });
})();
