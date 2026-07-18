(() => {
    const numberValue = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    const formatTime = (totalSeconds, durationSeconds) => {
        const safeSeconds = Math.max(0, Math.floor(totalSeconds));
        const hours = Math.floor(safeSeconds / 3600);
        const minutes = Math.floor((safeSeconds % 3600) / 60);
        const seconds = safeSeconds % 60;

        if (hours > 0 || durationSeconds >= 3600) {
            return [hours, minutes, seconds]
                .map((part) => String(part).padStart(2, "0"))
                .join(":");
        }

        return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    const labelsFor = (root) => ({
        countdown: root.dataset.labelCountdown || "Countdown",
        stopwatch: root.dataset.labelStopwatch || "Stopwatch",
        running: root.dataset.labelRunning || "Running",
        paused: root.dataset.labelPaused || "Paused",
        complete: root.dataset.labelComplete || "Complete",
    });

    const createTimerController = (overlay, labels) => {
        const time = overlay.querySelector("[data-timer-time]");
        const label = overlay.querySelector("[data-timer-label]");
        const modeLabel = overlay.querySelector("[data-timer-mode-label]");
        const status = overlay.querySelector("[data-timer-status]");
        const progressWrap = overlay.querySelector("[data-timer-progress-wrap]");

        let mode = overlay.dataset.mode || "countdown";
        let durationSeconds = numberValue(overlay.dataset.durationSeconds, 300);
        let baseSeconds = numberValue(overlay.dataset.displaySeconds, durationSeconds);
        let running = overlay.dataset.running === "true";
        let baselineAt = Date.now();
        let showProgress = !progressWrap?.hidden;

        const currentSeconds = () => {
            if (!running) {
                return baseSeconds;
            }

            const delta = Math.floor((Date.now() - baselineAt) / 1000);
            if (mode === "countdown") {
                return Math.max(baseSeconds - delta, 0);
            }
            return Math.min(baseSeconds + delta, (100 * 60 * 60) - 1);
        };

        const render = () => {
            const seconds = currentSeconds();
            const complete = mode === "countdown" && seconds <= 0;

            if (complete) {
                running = false;
                baseSeconds = 0;
            }

            if (time) {
                time.textContent = formatTime(seconds, durationSeconds);
                time.dateTime = `PT${seconds}S`;
            }

            if (modeLabel) {
                modeLabel.textContent = labels[mode];
            }

            if (status) {
                const state = complete ? "complete" : (running ? "running" : "paused");
                status.dataset.state = state;
                status.textContent = labels[state];
            }

            const progress = mode === "countdown" && durationSeconds > 0
                ? Math.min(Math.round(((durationSeconds - seconds) / durationSeconds) * 100), 100)
                : 0;
            overlay.style.setProperty("--timer-progress", `${progress}%`);

            if (progressWrap) {
                progressWrap.hidden = !showProgress || mode === "stopwatch";
                progressWrap.setAttribute("aria-valuenow", String(progress));
            }
        };

        const applyClock = (state) => {
            mode = state.mode || mode;
            durationSeconds = numberValue(state.duration_seconds, durationSeconds);
            baseSeconds = numberValue(state.display_seconds, mode === "countdown" ? durationSeconds : 0);
            running = Boolean(state.is_running);
            baselineAt = Date.now();
            overlay.dataset.mode = mode;
            overlay.dataset.durationSeconds = String(durationSeconds);
            overlay.dataset.displaySeconds = String(baseSeconds);
            overlay.dataset.running = String(running);
            render();
        };

        const applyDesign = (state) => {
            const design = state.design || {};
            const template = design.template || "glass";
            overlay.classList.remove("timer-overlay--minimal", "timer-overlay--glass", "timer-overlay--neon");
            overlay.classList.add(`timer-overlay--${template}`);
            overlay.style.setProperty("--timer-background", design.background_rgba || "rgba(17, 24, 39, .86)");
            overlay.style.setProperty("--timer-text", design.text_color || "#f8fafc");
            overlay.style.setProperty("--timer-accent", design.accent_color || "#8b5cf6");
            overlay.style.setProperty("--timer-border", design.border_color || "#a78bfa");
            overlay.style.setProperty("--timer-border-width", `${numberValue(design.border_width, 1)}px`);
            overlay.style.setProperty("--timer-radius", `${numberValue(design.corner_radius, 24)}px`);
            overlay.style.setProperty("--timer-width", `${numberValue(design.overlay_width, 520)}px`);
            overlay.style.setProperty("--timer-height", `${numberValue(design.overlay_height, 230)}px`);
            overlay.style.setProperty("--timer-label-size", `${numberValue(design.label_text_size, 16)}px`);
            overlay.style.setProperty("--timer-time-size", `${numberValue(design.timer_text_size, 76)}px`);
            overlay.style.setProperty("--timer-shadow", design.shadow_enabled === false ? "none" : (design.shadow_css || "0 20px 52px rgba(0, 0, 0, .38)"));
            showProgress = design.show_progress !== false;

            if (label) {
                label.textContent = state.label || "";
                label.hidden = !state.label;
            }
            render();
        };

        const applyState = (state, includeDesign = true) => {
            applyClock(state);
            if (includeDesign) {
                applyDesign(state);
            }
        };

        const fieldValue = (form, name, fallback = "") => {
            const field = form.elements.namedItem(name);
            return field ? field.value : fallback;
        };

        const applyForm = (form) => {
            const nextMode = fieldValue(form, "mode", mode);
            const hours = numberValue(fieldValue(form, "duration_hours", 0));
            const minutes = numberValue(fieldValue(form, "duration_minutes", 5));
            const seconds = numberValue(fieldValue(form, "duration_seconds_part", 0));
            const nextDuration = Math.max(1, (hours * 3600) + (minutes * 60) + seconds);

            if (nextMode !== mode || nextDuration !== durationSeconds) {
                mode = nextMode;
                durationSeconds = nextDuration;
                baseSeconds = mode === "countdown" ? durationSeconds : 0;
                baselineAt = Date.now();
                running = false;
            }

            const backgroundColor = fieldValue(form, "background_color", "#111827");
            const opacity = Math.min(Math.max(numberValue(fieldValue(form, "background_opacity", 86)), 0), 100);
            const red = Number.parseInt(backgroundColor.slice(1, 3), 16) || 17;
            const green = Number.parseInt(backgroundColor.slice(3, 5), 16) || 24;
            const blue = Number.parseInt(backgroundColor.slice(5, 7), 16) || 39;
            const design = {
                template: fieldValue(form, "design_template", "glass"),
                background_rgba: `rgba(${red}, ${green}, ${blue}, ${(opacity / 100).toFixed(2)})`,
                text_color: fieldValue(form, "text_color", "#f8fafc"),
                accent_color: fieldValue(form, "accent_color", "#8b5cf6"),
                border_color: fieldValue(form, "border_color", "#a78bfa"),
                border_width: fieldValue(form, "border_width", 1),
                corner_radius: fieldValue(form, "corner_radius", 24),
                overlay_width: fieldValue(form, "overlay_width", 520),
                overlay_height: fieldValue(form, "overlay_height", 230),
                label_text_size: fieldValue(form, "label_text_size", 16),
                timer_text_size: fieldValue(form, "timer_text_size", 76),
                show_progress: Boolean(form.elements.namedItem("show_progress")?.checked),
                shadow_enabled: Boolean(form.elements.namedItem("shadow_enabled")?.checked),
            };

            applyDesign({label: fieldValue(form, "label", ""), design});
            render();
        };

        render();
        return {applyForm, applyState, render};
    };

    const controllers = new Map();
    document.querySelectorAll("[data-timer-overlay]").forEach((overlay) => {
        const labelsRoot = overlay.closest("[data-timer-editor], [data-timer-source]") || document.body;
        controllers.set(overlay, createTimerController(overlay, labelsFor(labelsRoot)));
    });

    window.setInterval(() => {
        controllers.forEach((controller) => controller.render());
    }, 200);

    const source = document.querySelector("[data-timer-source]");
    if (source) {
        const overlay = source.querySelector("[data-timer-overlay]");
        const controller = controllers.get(overlay);

        const poll = async () => {
            try {
                const response = await fetch(source.dataset.stateUrl, {
                    cache: "no-store",
                    headers: {Accept: "application/json"},
                });
                if (response.ok) {
                    controller?.applyState(await response.json());
                }
            } catch {
                // OBS keeps rendering the locally advancing clock during short outages.
            }
        };

        window.setInterval(poll, 1200);
        poll();
    }

    const editor = document.querySelector("[data-timer-editor]");
    if (editor) {
        const form = editor.querySelector("[data-timer-form]");
        const overlay = editor.querySelector("[data-timer-overlay]");
        const controller = controllers.get(overlay);
        const controls = editor.querySelector("[data-timer-controls]");
        const controlStatus = editor.querySelector("[data-control-status]");

        if (form && controller) {
            const updatePreview = () => controller.applyForm(form);
            form.addEventListener("input", updatePreview);
            form.addEventListener("change", updatePreview);
            form.addEventListener("nexora:editor-restore", updatePreview);
            updatePreview();
        }

        controls?.addEventListener("click", async (event) => {
            const button = event.target.closest("[data-timer-action]");
            if (!button) {
                return;
            }

            const buttons = Array.from(controls.querySelectorAll("button"));
            const body = new FormData();
            body.set("action", button.dataset.timerAction);
            body.set("csrfmiddlewaretoken", controls.querySelector("[name='csrfmiddlewaretoken']")?.value || "");
            buttons.forEach((candidate) => { candidate.disabled = true; });

            try {
                const response = await fetch(controls.dataset.controlUrl, {
                    method: "POST",
                    body,
                    credentials: "same-origin",
                    headers: {Accept: "application/json", "X-Requested-With": "XMLHttpRequest"},
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.error || "Timer control failed");
                }
                controller?.applyState(payload, false);
                if (controlStatus) {
                    controlStatus.textContent = button.textContent.trim();
                }
            } catch (error) {
                if (controlStatus) {
                    controlStatus.textContent = error.message;
                }
            } finally {
                buttons.forEach((candidate) => { candidate.disabled = false; });
            }
        });
    }

    const toast = document.querySelector("[data-copy-toast]");
    let toastTimer;
    const showToast = () => {
        if (!toast) return;
        toast.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2200);
    };

    const copyText = async (value) => {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(value);
            return;
        }
        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    };

    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");
        if (!copyButton) return;

        try {
            await copyText(copyButton.dataset.copyUrl);
            showToast();
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
