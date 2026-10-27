(() => {
    const STAGE_WIDTH = 1920;
    const STAGE_HEIGHT = 1080;
    const DEFAULT_SHADOW = "0 32px 90px rgba(0, 0, 0, 0.45)";

    const numberValue = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    const formatCountdown = (totalSeconds) => {
        const safeSeconds = Math.max(0, Math.floor(totalSeconds));
        const hours = Math.floor(safeSeconds / 3600);
        const minutes = String(Math.floor((safeSeconds % 3600) / 60)).padStart(2, "0");
        const seconds = String(safeSeconds % 60).padStart(2, "0");
        return hours ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
    };

    // The scene is laid out at 1920 × 1080 and scaled to fit its frame, centered.
    const fitStage = (frame) => {
        const stage = frame.querySelector("[data-scene-overlay]");
        if (!stage || !frame.clientWidth || !frame.clientHeight) return;
        const scale = Math.min(frame.clientWidth / STAGE_WIDTH, frame.clientHeight / STAGE_HEIGHT);
        stage.style.transform = `scale(${scale})`;
        stage.style.left = `${(frame.clientWidth - STAGE_WIDTH * scale) / 2}px`;
        stage.style.top = `${(frame.clientHeight - STAGE_HEIGHT * scale) / 2}px`;
    };

    const createController = (overlay) => {
        const headline = overlay.querySelector("[data-scene-headline]");
        const message = overlay.querySelector("[data-scene-message]");
        const countdown = overlay.querySelector("[data-scene-countdown]");
        let hasCountdown = overlay.dataset.hasCountdown === "true";
        let baseSeconds = numberValue(overlay.dataset.countdownSeconds);
        let baselineAt = Date.now();

        const render = () => {
            if (!countdown) return;
            countdown.hidden = !hasCountdown;
            const elapsed = Math.floor((Date.now() - baselineAt) / 1000);
            countdown.textContent = formatCountdown(baseSeconds - elapsed);
        };

        const applyContent = (state) => {
            overlay.dataset.scene = state.scene || overlay.dataset.scene;
            if (headline) headline.textContent = state.headline || "";
            if (message) {
                message.textContent = state.message || "";
                message.hidden = !state.message;
            }
        };

        const applyCountdown = (state) => {
            hasCountdown = Boolean(state.has_countdown);
            baseSeconds = numberValue(state.countdown_seconds);
            baselineAt = Date.now();
            render();
        };

        const applyDesign = (design = {}) => {
            overlay.classList.remove("scene-overlay--minimal", "scene-overlay--glass", "scene-overlay--neon");
            overlay.classList.add(`scene-overlay--${design.template || "glass"}`);
            overlay.style.setProperty("--scene-background", design.background_rgba || "rgba(11, 16, 32, 1)");
            overlay.style.setProperty("--scene-text", design.text_color || "#f8fafc");
            overlay.style.setProperty("--scene-accent", design.accent_color || "#8b5cf6");
            overlay.style.setProperty("--scene-border", design.border_color || "#a78bfa");
            overlay.style.setProperty("--scene-border-width", `${numberValue(design.border_width, 1)}px`);
            overlay.style.setProperty("--scene-radius", `${numberValue(design.corner_radius, 32)}px`);
            overlay.style.setProperty("--scene-headline-size", `${numberValue(design.headline_text_size, 96)}px`);
            overlay.style.setProperty("--scene-message-size", `${numberValue(design.message_text_size, 30)}px`);
            overlay.style.setProperty("--scene-shadow", design.shadow_css || "none");
            if (["font_family", "font_url", "logo_url", "background_image_url"].some((key) => key in design)) {
                window.NexoraBranding?.apply(overlay, design);
            }
        };

        const applyState = (state) => {
            applyContent(state);
            applyCountdown(state);
            applyDesign(state.design);
        };

        render();
        return {applyContent, applyCountdown, applyDesign, applyState, render};
    };

    const frames = document.querySelectorAll("[data-scene-frame]");
    frames.forEach((frame) => {
        fitStage(frame);
        if (window.ResizeObserver) new ResizeObserver(() => fitStage(frame)).observe(frame);
        else window.addEventListener("resize", () => fitStage(frame));
    });

    const controllers = new Map();
    document.querySelectorAll("[data-scene-overlay]").forEach((overlay) => {
        controllers.set(overlay, createController(overlay));
    });
    window.setInterval(() => controllers.forEach((controller) => controller.render()), 250);

    const source = document.querySelector("[data-scene-source]");
    if (source && window.NexoraPolling) {
        const controller = controllers.get(source.querySelector("[data-scene-overlay]"));
        window.NexoraPolling.start({
            url: source.dataset.stateUrl,
            interval: 1500,
            hiddenInterval: 10000,
            onData: (state) => controller?.applyState(state),
        });
    }

    const editor = document.querySelector("[data-scene-editor]");
    if (editor) {
        const form = editor.querySelector("[data-scene-form]");
        const overlay = editor.querySelector("[data-scene-overlay]");
        const controller = controllers.get(overlay);
        const controls = editor.querySelector("[data-scene-controls]");
        const controlStatus = editor.querySelector("[data-control-status]");
        const previewLabel = editor.querySelector("[data-scene-preview-label]");
        const sceneLabels = Object.fromEntries(
            Array.from(editor.querySelectorAll("[data-scene-fields]")).map((fieldset) => [
                fieldset.dataset.sceneFields,
                fieldset.querySelector("legend")?.textContent.trim() || fieldset.dataset.sceneFields,
            ]),
        );
        // The live scene keeps its running countdown; other scenes preview their configured one.
        const isCreate = editor.dataset.editorCreate === "true";
        let liveScene = overlay?.dataset.scene || "starting";
        let liveHasCountdown = overlay?.dataset.hasCountdown === "true";
        let liveEndsAt = Date.now() + numberValue(overlay?.dataset.countdownSeconds) * 1000;
        let previewScene = liveScene;

        const liveCountdown = () => ({
            has_countdown: liveHasCountdown,
            countdown_seconds: Math.max(Math.ceil((liveEndsAt - Date.now()) / 1000), 0),
        });

        const fieldValue = (name, fallback = "") => {
            const field = form?.elements.namedItem(name);
            return field ? field.value : fallback;
        };

        const designFromForm = () => {
            const color = fieldValue("background_color", "#0b1020");
            const opacity = Math.min(Math.max(numberValue(fieldValue("background_opacity", 100)), 0), 100);
            const [red, green, blue] = [1, 3, 5].map((offset) => Number.parseInt(color.slice(offset, offset + 2), 16) || 0);
            return {
                template: fieldValue("design_template", "glass"),
                background_rgba: `rgba(${red}, ${green}, ${blue}, ${(opacity / 100).toFixed(2)})`,
                text_color: fieldValue("text_color", "#f8fafc"),
                accent_color: fieldValue("accent_color", "#8b5cf6"),
                border_color: fieldValue("border_color", "#a78bfa"),
                border_width: fieldValue("border_width", 1),
                corner_radius: fieldValue("corner_radius", 32),
                headline_text_size: fieldValue("headline_text_size", 96),
                message_text_size: fieldValue("message_text_size", 30),
                shadow_css: form?.elements.namedItem("shadow_enabled")?.checked ? DEFAULT_SHADOW : "none",
            };
        };

        const updatePreview = () => {
            if (!controller) return;
            controller.applyContent({
                scene: previewScene,
                headline: fieldValue(`${previewScene}_headline`).trim(),
                message: fieldValue(`${previewScene}_message`).trim(),
            });
            const minutes = numberValue(fieldValue(`${previewScene}_countdown_minutes`, 0));
            controller.applyCountdown(previewScene === liveScene && !isCreate
                ? liveCountdown()
                : {has_countdown: minutes > 0, countdown_seconds: minutes * 60});
            controller.applyDesign(designFromForm());
            if (previewLabel) previewLabel.textContent = sceneLabels[previewScene] || previewScene;
        };

        if (form) {
            form.addEventListener("input", updatePreview);
            form.addEventListener("change", updatePreview);
            form.addEventListener("nexora:editor-restore", updatePreview);
            form.addEventListener("focusin", (event) => {
                const fieldset = event.target.closest("[data-scene-fields]");
                if (fieldset && fieldset.dataset.sceneFields !== previewScene) {
                    previewScene = fieldset.dataset.sceneFields;
                    updatePreview();
                }
            });
            updatePreview();
        }

        controls?.addEventListener("click", async (event) => {
            const button = event.target.closest("[data-scene-action]");
            if (!button) return;

            const buttons = Array.from(controls.querySelectorAll("button"));
            const body = new FormData();
            body.set("action", button.dataset.sceneAction);
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
                if (!response.ok) throw new Error(payload.error || "Scene control failed");
                liveScene = payload.scene;
                liveHasCountdown = payload.has_countdown;
                liveEndsAt = Date.now() + payload.countdown_seconds * 1000;
                previewScene = liveScene;
                buttons.forEach((candidate) => {
                    if (candidate.dataset.sceneAction !== "restart") {
                        candidate.setAttribute("aria-pressed", String(candidate.dataset.sceneAction === liveScene));
                    }
                });
                updatePreview();
                if (controlStatus) controlStatus.textContent = button.textContent.trim();
            } catch (error) {
                if (controlStatus) controlStatus.textContent = error.message;
            } finally {
                buttons.forEach((candidate) => { candidate.disabled = false; });
            }
        });
    }

    const toast = document.querySelector("[data-copy-toast]");
    let toastTimer;
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
