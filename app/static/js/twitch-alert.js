(() => {
    const TEMPLATES = ["minimal", "glass", "neon"];
    const ICONS = {follow: "♥", subscription: "★", gift: "✦", cheer: "◆", raid: "➤"};
    const MAX_QUEUE = 20;
    const LEAVE_MS = 450;
    const GAP_MS = 600;

    const numberValue = (value, fallback = 0) => {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    };

    const playSound = (sound, volume = 70) => {
        if (!sound || sound === "none" || volume <= 0) return;
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        try {
            const context = new AudioContext();
            const patterns = {
                chime: [[523, 0], [659, .13], [784, .26]],
                fanfare: [[392, 0], [523, .12], [659, .24], [784, .38], [1046, .54]],
                arcade: [[440, 0], [660, .1], [880, .2], [1320, .34]],
                sparkle: [[1046, 0], [1318, .08], [1568, .16], [2093, .25]],
            };
            const wave = sound === "arcade" ? "square" : "sine";
            (patterns[sound] || patterns.chime).forEach(([frequency, offset], index, notes) => {
                const oscillator = context.createOscillator();
                const gain = context.createGain();
                oscillator.type = wave;
                oscillator.frequency.value = frequency;
                const start = context.currentTime + offset;
                const end = start + (sound === "fanfare" && index === notes.length - 1 ? .5 : .28);
                gain.gain.setValueAtTime(0.0001, start);
                gain.gain.exponentialRampToValueAtTime(Math.max(volume / 100, .01) * .16, start + .025);
                gain.gain.exponentialRampToValueAtTime(.0001, end);
                oscillator.connect(gain).connect(context.destination);
                oscillator.start(start);
                oscillator.stop(end + .02);
            });
            window.setTimeout(() => context.close().catch(() => {}), 1500);
        } catch { /* Audio is optional in restricted browser contexts. */ }
    };

    // Builds "{name} cheered {amount} bits!" as DOM nodes; viewer names never touch innerHTML.
    const fillTitle = (node, template, event) => {
        node.replaceChildren();
        String(template || "{name}").split(/(\{name\}|\{amount\})/).forEach((part) => {
            if (part === "{name}" || part === "{amount}") {
                const strong = document.createElement("strong");
                strong.textContent = part === "{name}"
                    ? event.name
                    : numberValue(event.amount).toLocaleString();
                node.append(strong);
            } else if (part) {
                node.append(document.createTextNode(part));
            }
        });
    };

    const createAlerts = (overlay, initialState, {sampleEvent = null} = {}) => {
        const card = overlay.querySelector("[data-alert-card]");
        const icon = card.querySelector("[data-alert-icon]");
        const title = card.querySelector("[data-alert-title]");
        const message = card.querySelector("[data-alert-message]");
        let settings = initialState.settings || {};
        let design = {};
        let queue = [];
        let playing = false;
        let shownEvent = null;
        let lastSeenId = Math.max(0, ...(initialState.events || []).map((event) => event.id || 0));

        const render = (event) => {
            shownEvent = event;
            card.dataset.type = event.type;
            icon.textContent = ICONS[event.type] || ICONS.follow;
            fillTitle(title, (settings.texts || {})[event.type], event);
            const showMessage = Boolean(settings.show_user_message && event.message);
            message.textContent = showMessage ? event.message : "";
            message.hidden = !showMessage;
        };

        const rest = () => {
            card.classList.remove("is-entering", "is-leaving");
            if (sampleEvent) {
                render(sampleEvent);
                card.hidden = false;
            } else {
                card.hidden = true;
            }
        };

        const next = () => {
            const event = queue.shift();
            if (!event) {
                playing = false;
                rest();
                return;
            }
            playing = true;
            render(event);
            card.hidden = false;
            card.classList.remove("is-entering", "is-leaving");
            void card.offsetWidth;
            card.classList.add("is-entering");
            playSound(settings.sound, numberValue(settings.volume, 70));
            const duration = Math.max(numberValue(settings.duration_seconds, 6), 2) * 1000;
            window.setTimeout(() => {
                card.classList.add("is-leaving");
                window.setTimeout(() => {
                    card.hidden = true;
                    window.setTimeout(next, GAP_MS);
                }, LEAVE_MS);
            }, duration);
        };

        const play = (event) => {
            queue.push(event);
            if (queue.length > MAX_QUEUE) queue = queue.slice(-MAX_QUEUE);
            if (!playing) next();
        };

        const applySettings = (nextSettings = {}) => {
            settings = {...settings, ...nextSettings};
            if (shownEvent) render(shownEvent);
        };

        const applyDesign = (nextDesign = {}) => {
            design = {...design, ...nextDesign};
            overlay.classList.remove(...TEMPLATES.map((template) => `alert-overlay--${template}`));
            overlay.classList.add(`alert-overlay--${TEMPLATES.includes(design.template) ? design.template : "glass"}`);
            overlay.dataset.animation = design.animation || "pop";
            overlay.dataset.shadow = String(design.shadow_enabled !== false);
            const properties = {
                "--alert-background": design.background_rgba,
                "--alert-text": design.text_color,
                "--alert-accent": design.accent_color,
                "--alert-border": design.border_color,
                "--alert-border-width": `${numberValue(design.border_width, 2)}px`,
                "--alert-radius": String(numberValue(design.corner_radius, 24)),
                "--alert-font-size": String(numberValue(design.font_size, 34)),
            };
            Object.entries(properties).forEach(([name, value]) => {
                if (value) overlay.style.setProperty(name, value);
            });
            if (["font_family", "font_url", "logo_url", "background_image_url"].some((key) => key in nextDesign)) {
                window.NexoraBranding?.apply(overlay, design);
            }
        };

        // Only events newer than the last one seen play, so reloading OBS replays nothing.
        const applyState = (state) => {
            applySettings(state.settings);
            applyDesign(state.design);
            (state.events || [])
                .filter((event) => event.id > lastSeenId)
                .forEach((event) => {
                    lastSeenId = event.id;
                    play(event);
                });
        };

        applyDesign(initialState.design);
        rest();
        return {play, applySettings, applyDesign, applyState};
    };

    const overlay = document.querySelector("[data-alert-overlay]");
    const initialStateNode = document.getElementById("twitch-alert-initial-state");
    if (!overlay || !initialStateNode) return;
    const initialState = JSON.parse(initialStateNode.textContent);

    const source = document.querySelector("[data-alert-source]");
    if (source) {
        const alerts = createAlerts(overlay, initialState);
        window.NexoraPolling?.start({
            url: source.dataset.stateUrl,
            interval: 2000,
            hiddenInterval: 4000,
            onData: alerts.applyState,
        });
        return;
    }

    const editor = document.querySelector("[data-alert-editor]");
    if (!editor) return;
    const form = editor.querySelector("[data-alert-form]");
    const sampleEvent = {type: "follow", name: "NexoraFan", amount: 0, message: ""};
    const alerts = createAlerts(overlay, initialState, {sampleEvent});

    const fieldValue = (name, fallback = "") => {
        const field = form?.elements.namedItem(name);
        return field ? field.value : fallback;
    };
    const checked = (name) => Boolean(form?.elements.namedItem(name)?.checked);

    const textsFromForm = () => Object.fromEntries(
        Array.from(form.querySelectorAll("[data-alert-text]")).map((field) => [
            field.dataset.alertText,
            field.value.trim() || field.dataset.defaultText,
        ]),
    );

    const updatePreview = () => {
        const color = fieldValue("background_color", "#0b1020");
        const opacity = Math.min(Math.max(numberValue(fieldValue("background_opacity", 86)), 0), 100);
        const [red, green, blue] = [1, 3, 5].map((offset) => Number.parseInt(color.slice(offset, offset + 2), 16) || 0);
        alerts.applySettings({
            duration_seconds: numberValue(fieldValue("alert_duration_seconds", 6), 6),
            show_user_message: checked("show_user_message"),
            texts: textsFromForm(),
            sound: fieldValue("sound_type", "chime"),
            volume: numberValue(fieldValue("sound_volume", 70), 70),
        });
        alerts.applyDesign({
            template: fieldValue("design_template", "glass"),
            animation: fieldValue("animation", "pop"),
            background_rgba: `rgba(${red}, ${green}, ${blue}, ${(opacity / 100).toFixed(2)})`,
            text_color: fieldValue("text_color", "#f8fafc"),
            accent_color: fieldValue("accent_color", "#9146ff"),
            border_color: fieldValue("border_color", "#a78bfa"),
            border_width: fieldValue("border_width", 2),
            corner_radius: fieldValue("corner_radius", 24),
            font_size: fieldValue("font_size", 34),
            shadow_enabled: checked("shadow_enabled"),
        });
    };
    if (form) {
        form.addEventListener("input", updatePreview);
        form.addEventListener("change", updatePreview);
        form.addEventListener("nexora:editor-restore", updatePreview);
    }
    updatePreview();

    const previewEvents = {
        follow: {amount: 0, message: ""},
        subscription: {amount: 6, message: ""},
        gift: {amount: 5, message: ""},
        cheer: {amount: 500, message: ""},
        raid: {amount: 42, message: ""},
    };
    const csrfToken = () => editor.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

    editor.querySelectorAll("[data-alert-test]").forEach((button) => {
        button.addEventListener("click", async () => {
            const type = button.dataset.alertTest;
            const testUrl = editor.dataset.testUrl;
            if (!testUrl) {
                alerts.play({type, name: "NexoraFan", ...previewEvents[type]});
                return;
            }
            button.disabled = true;
            try {
                const response = await fetch(testUrl, {
                    method: "POST",
                    headers: {"X-CSRFToken": csrfToken(), Accept: "application/json"},
                    body: new URLSearchParams({event_type: type}),
                    credentials: "same-origin",
                });
                const data = await response.json();
                alerts.play(data.ok ? data.event : {type, name: "NexoraFan", ...previewEvents[type]});
            } catch {
                alerts.play({type, name: "NexoraFan", ...previewEvents[type]});
            } finally {
                button.disabled = false;
            }
        });
    });

    const toast = document.querySelector("[data-copy-toast]");
    let toastTimer;
    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");
        if (!copyButton) return;
        try {
            await navigator.clipboard.writeText(copyButton.dataset.copyUrl);
            if (toast) {
                toast.hidden = false;
                window.clearTimeout(toastTimer);
                toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2200);
            }
        } catch {
            window.prompt(copyButton.textContent.trim(), copyButton.dataset.copyUrl);
        }
    });

    document.addEventListener("submit", (event) => {
        const deleteForm = event.target.closest("[data-confirm-delete]");
        if (deleteForm && !window.confirm(deleteForm.dataset.confirmDelete)) {
            event.preventDefault();
        }
    });
})();
