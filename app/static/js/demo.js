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

    const updateTwitchGoal = (card) => {
        const preview = card.querySelector("[data-demo-preview]");
        const target = Math.max(1, Math.round(numberValue(card, "target", 1000)));
        const current = Math.max(0, Math.round(numberValue(card, "current", 842)));
        const progress = Math.min((current / target) * 100, 100);

        card.querySelector('[data-demo-output="title"]').textContent = textValue(card, "title", "Road to 1,000");
        card.querySelector('[data-demo-output="score"]').textContent = `${current.toLocaleString()} / ${target.toLocaleString()}`;
        card.querySelector("[data-demo-progress]").style.width = `${progress}%`;
        preview.style.setProperty(
            "--demo-accent",
            card.querySelector('[data-demo-field="accent"]')?.value || "#9146ff",
        );
    };

    const formatClock = (totalSeconds) => {
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    // The timer demo keeps its own countdown state; editing the minutes resets it.
    const timerState = new WeakMap();

    const timerFor = (card) => {
        if (!timerState.has(card)) {
            timerState.set(card, { duration: 300, remaining: 300, intervalId: null });
        }
        return timerState.get(card);
    };

    const renderTimer = (card) => {
        const state = timerFor(card);
        card.querySelector('[data-demo-output="time"]').textContent = formatClock(state.remaining);
        card.querySelector("[data-demo-progress]").style.width = `${(state.remaining / state.duration) * 100}%`;
        const toggle = card.querySelector('[data-demo-action="toggle"]');
        toggle.textContent = state.intervalId ? toggle.dataset.pauseLabel : toggle.dataset.startLabel;
    };

    const stopTimer = (card) => {
        const state = timerFor(card);
        window.clearInterval(state.intervalId);
        state.intervalId = null;
    };

    const updateTimer = (card, event) => {
        const state = timerFor(card);
        const preview = card.querySelector("[data-demo-preview]");

        if (!event || event.target.dataset.demoField === "minutes") {
            stopTimer(card);
            state.duration = Math.max(1, Math.min(180, Math.round(numberValue(card, "minutes", 5)))) * 60;
            state.remaining = state.duration;
        }

        card.querySelector('[data-demo-output="title"]').textContent = textValue(card, "title", "Starting soon");
        preview.style.setProperty(
            "--demo-accent",
            card.querySelector('[data-demo-field="accent"]')?.value || "#8b5cf6",
        );
        renderTimer(card);
    };

    const bindTimerActions = (card) => {
        card.querySelector('[data-demo-action="toggle"]').addEventListener("click", () => {
            const state = timerFor(card);
            if (state.intervalId) {
                stopTimer(card);
            } else {
                if (state.remaining === 0) {
                    state.remaining = state.duration;
                }
                state.intervalId = window.setInterval(() => {
                    state.remaining = Math.max(0, state.remaining - 1);
                    if (state.remaining === 0) {
                        stopTimer(card);
                    }
                    renderTimer(card);
                }, 1000);
            }
            renderTimer(card);
        });

        card.querySelector('[data-demo-action="reset"]').addEventListener("click", () => {
            const state = timerFor(card);
            stopTimer(card);
            state.remaining = state.duration;
            renderTimer(card);
        });
    };

    const updateScore = (card) => {
        const preview = card.querySelector("[data-demo-preview]");
        const score = (name) => Math.max(0, Math.min(999, Math.round(numberValue(card, name, 0))));

        card.querySelector('[data-demo-output="player-a"]').textContent = textValue(card, "player-a", "Nova");
        card.querySelector('[data-demo-output="player-b"]').textContent = textValue(card, "player-b", "Pixel");
        card.querySelector('[data-demo-output="score-a"]').textContent = String(score("score-a"));
        card.querySelector('[data-demo-output="score-b"]').textContent = String(score("score-b"));
        preview.style.setProperty(
            "--demo-accent",
            card.querySelector('[data-demo-field="accent"]')?.value || "#38bdf8",
        );
    };

    cards.forEach((card) => {
        const update = {
            spotify: updateSpotify,
            "twitch-goal": updateTwitchGoal,
            winchallenge: updateWinChallenge,
            timer: updateTimer,
            score: updateScore,
        }[card.dataset.demoCard];

        if (card.dataset.demoCard === "timer") {
            bindTimerActions(card);
        }
        const preview = card.querySelector("[data-demo-preview]");

        card.addEventListener("input", (event) => update(card, event));

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
