(() => {
    const number = (value, fallback = 0) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    const clamp = (value, min, max) => Math.min(Math.max(number(value, min), min), max);
    const clone = (value) => JSON.parse(JSON.stringify(value));
    const parseScript = (id, fallback = {}) => {
        try { return JSON.parse(document.getElementById(id)?.textContent || ""); }
        catch { return fallback; }
    };
    const formatValue = (value, state) => {
        if (value === null || value === undefined) return "—";
        return `${state.number_prefix || ""}${new Intl.NumberFormat().format(value)}${state.number_suffix || ""}`;
    };

    const elementText = (type, state) => {
        const goal = state.goal || {};
        if (type === "title") return state.title || "Twitch Goal";
        if (type === "channel_name") return state.channel?.display_name || "NexoraCreator";
        if (type === "current") return formatValue(goal.current_value, state);
        if (type === "target") return formatValue(goal.target_value, state);
        if (type === "progress_text") return `${formatValue(goal.current_value, state)} / ${formatValue(goal.target_value, state)}`;
        if (type === "percentage") return `${Math.round(number(goal.progress_percent))}%`;
        if (type === "remaining") return `${formatValue(goal.remaining, state)} remaining`;
        if (type === "icon") return state.goal_type === "subscriptions" ? "★" : "♥";
        return "";
    };

    const createContent = (node, element, state) => {
        const type = element.type;
        if (type === "channel_avatar") {
            const wrapper = document.createElement("span");
            wrapper.className = "twitch-goal-avatar";
            const url = state.channel?.avatar_url || "";
            if (url) {
                const image = document.createElement("img");
                image.src = url;
                image.alt = "";
                image.dataset.channelAvatar = "";
                wrapper.append(image);
            } else {
                const fallback = document.createElement("b");
                fallback.textContent = (state.channel?.display_name || "N").slice(0, 1).toUpperCase();
                wrapper.append(fallback);
            }
            node.append(wrapper);
            return;
        }
        if (type === "progress_bar") {
            const track = document.createElement("span");
            track.className = "twitch-goal-progress";
            const fill = document.createElement("i");
            fill.style.width = `${clamp(state.goal?.progress_percent, 0, 100)}%`;
            track.append(fill);
            node.append(track);
            return;
        }
        if (type === "progress_ring") {
            node.innerHTML = `<svg class="twitch-goal-ring" viewBox="0 0 120 120" aria-hidden="true"><circle class="twitch-goal-ring__track" cx="60" cy="60" r="52"></circle><circle class="twitch-goal-ring__fill" cx="60" cy="60" r="52" pathLength="100"></circle></svg>`;
            node.querySelector(".twitch-goal-ring__fill").style.strokeDashoffset = String(100 - clamp(state.goal?.progress_percent, 0, 100));
            return;
        }
        if (type === "logo") {
            if (state.logo_url) {
                const image = document.createElement("img");
                image.className = "twitch-goal-logo";
                image.src = state.logo_url;
                image.alt = "";
                image.dataset.overlayCustomLogo = "";
                node.append(image);
            } else {
                node.textContent = "N";
            }
            return;
        }
        const span = document.createElement("span");
        if (type === "icon") span.className = "twitch-goal-icon";
        span.textContent = elementText(type, state);
        node.append(span);
    };

    const renderElements = (canvas, elements, state, editor = false, selectedId = null) => {
        canvas.querySelectorAll("[data-goal-element]").forEach((node) => node.remove());
        elements.forEach((element) => {
            const node = document.createElement("div");
            node.className = `twitch-goal-element twitch-goal-element--${element.type}`;
            node.dataset.goalElement = "";
            node.dataset.elementId = element.id;
            node.dataset.elementType = element.type;
            Object.assign(node.style, {
                left: `${number(element.x)}px`, top: `${number(element.y)}px`,
                width: `${number(element.width, 120)}px`, height: `${number(element.height, 40)}px`,
                color: element.color || "#ffffff", fontSize: `${number(element.font_size, 20)}px`,
                fontWeight: String(number(element.font_weight, 700)),
                borderRadius: `${number(element.border_radius, 12)}px`,
                textAlign: element.text_align || "left", zIndex: String(number(element.z_index, 1)),
            });
            node.style.setProperty("--element-color", element.color || "#ffffff");
            node.style.setProperty("--element-background", element.background_color || "#27213f");
            node.style.setProperty("--goal-ring-width", number(element.stroke_width, 9));
            const visible = element.visible !== false;
            if (editor) {
                node.tabIndex = 0;
                node.setAttribute("role", "button");
                node.classList.toggle("is-selected", element.id === selectedId);
                node.classList.toggle("is-hidden-element", !visible);
                if (element.id === selectedId) {
                    const handle = document.createElement("span");
                    handle.className = "goal-resize-handle";
                    handle.dataset.resizeHandle = "";
                    node.append(handle);
                }
            }
            if (!editor && !visible) node.hidden = true;
            createContent(node, element, state);
            canvas.append(node);
        });
    };

    const designFromForm = (form, fallback = {}) => ({
        ...fallback,
        title: form.querySelector("#id_title")?.value || "Twitch Goal",
        goal_type: form.querySelector("#id_goal_type")?.value || "followers",
        number_prefix: form.querySelector("#id_number_prefix")?.value || "",
        number_suffix: form.querySelector("#id_number_suffix")?.value || "",
        canvas_width: number(form.querySelector("#id_canvas_width")?.value, 900),
        canvas_height: number(form.querySelector("#id_canvas_height")?.value, 160),
        background_color: form.querySelector("#id_background_color")?.value || "#120c24",
        background_opacity: number(form.querySelector("#id_background_opacity")?.value, 94),
        text_color: form.querySelector("#id_text_color")?.value || "#ffffff",
        accent_color: form.querySelector("#id_accent_color")?.value || "#9146ff",
        secondary_color: form.querySelector("#id_secondary_color")?.value || "#bf94ff",
        track_color: form.querySelector("#id_track_color")?.value || "#2c2440",
        border_color: form.querySelector("#id_border_color")?.value || "#a970ff",
        border_width: number(form.querySelector("#id_border_width")?.value, 1),
        corner_radius: number(form.querySelector("#id_corner_radius")?.value, 28),
        use_gradient: Boolean(form.querySelector("#id_use_gradient")?.checked),
        shadow_enabled: Boolean(form.querySelector("#id_shadow_enabled")?.checked),
    });

    const applyDesign = (canvas, design) => {
        const hex = design.background_color || "#120c24";
        const rgb = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
        canvas.style.setProperty("--goal-canvas-width", `${number(design.canvas_width, 900)}px`);
        canvas.style.setProperty("--goal-canvas-height", `${number(design.canvas_height, 160)}px`);
        canvas.style.setProperty("--goal-background", `rgba(${rgb.join(",")},${clamp(design.background_opacity, 0, 100) / 100})`);
        canvas.style.setProperty("--goal-text", design.text_color || "#fff");
        canvas.style.setProperty("--goal-accent", design.accent_color || "#9146ff");
        canvas.style.setProperty("--goal-secondary", design.secondary_color || "#bf94ff");
        canvas.style.setProperty("--goal-fill", design.use_gradient
            ? `linear-gradient(90deg, ${design.accent_color || "#9146ff"}, ${design.secondary_color || "#bf94ff"})`
            : (design.accent_color || "#9146ff"));
        canvas.style.setProperty("--goal-track", design.track_color || "#2c2440");
        canvas.style.setProperty("--goal-border", design.border_color || "#a970ff");
        canvas.style.setProperty("--goal-border-width", `${clamp(design.border_width, 0, 24)}px`);
        canvas.style.setProperty("--goal-radius", `${clamp(design.corner_radius, 0, 100)}px`);
        canvas.style.setProperty("--goal-shadow", design.shadow_enabled ? "0 22px 64px rgba(0,0,0,.42)" : "none");
    };

    const scalePreview = (shell) => {
        const canvas = shell.querySelector("[data-twitch-goal-canvas]");
        if (!canvas || shell.closest(".twitch-goal-source")) return;
        const width = number(getComputedStyle(canvas).getPropertyValue("--goal-canvas-width"), 900);
        const height = number(getComputedStyle(canvas).getPropertyValue("--goal-canvas-height"), 160);
        const padding = 24;
        const scale = Math.min(Math.max(shell.clientWidth - padding * 2, 1) / width, 650 / height, 1);
        const renderedWidth = width * scale;
        canvas.style.left = `${Math.max((shell.clientWidth - renderedWidth) / 2, 0)}px`;
        canvas.style.top = `${padding}px`;
        canvas.style.transform = `scale(${scale})`;
        canvas._goalScale = scale;
        shell.style.height = `${height * scale + padding * 2}px`;
    };

    const scalePublic = (body) => {
        const frame = body.querySelector("[data-goal-scale-shell]");
        if (!frame) return;
        const baseWidth = number(body.dataset.sourceWidth, 1080);
        const baseHeight = number(body.dataset.sourceHeight, 400);
        const scale = Math.max(Math.min(window.innerWidth / baseWidth, window.innerHeight / baseHeight), .05);
        frame.style.width = `${baseWidth}px`;
        frame.style.height = `${baseHeight}px`;
        frame.style.transform = `translate(-50%, -50%) scale(${scale})`;
    };

    const playSound = (sound, volume = 70) => {
        if (!sound || sound === "none") return;
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

    const playParticles = (canvas, options) => {
        if (!canvas) return () => {};
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.max(Math.round(rect.width * dpr), 1);
        canvas.height = Math.max(Math.round(rect.height * dpr), 1);
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const count = {low: 40, medium: 80, high: 140}[options.intensity] || 80;
        const colors = [options.primary_color || "#9146ff", options.secondary_color || "#fff", "#facc15"];
        const particles = Array.from({length: count}, (_, index) => {
            const firework = options.type === "fireworks";
            const angle = Math.random() * Math.PI * 2;
            const speed = firework ? 2 + Math.random() * 6 : 1 + Math.random() * 4;
            return {
                x: firework ? rect.width * (.25 + Math.random() * .5) : Math.random() * rect.width,
                y: firework ? rect.height * (.2 + Math.random() * .4) : options.type === "particles" ? -20 - Math.random() * rect.height : -20,
                vx: firework ? Math.cos(angle) * speed : (Math.random() - .5) * 3,
                vy: firework ? Math.sin(angle) * speed : 1 + Math.random() * 4,
                size: 3 + Math.random() * 8,
                color: colors[index % colors.length],
                rotation: Math.random() * Math.PI,
                life: 1,
            };
        });
        let frameId;
        let previous = performance.now();
        const start = previous;
        const duration = clamp(options.duration, 1, 10) * 1000;
        const draw = (now) => {
            const dt = Math.min((now - previous) / 16.67, 3);
            previous = now;
            ctx.clearRect(0, 0, rect.width, rect.height);
            particles.forEach((particle) => {
                particle.x += particle.vx * dt;
                particle.y += particle.vy * dt;
                particle.vy += .055 * dt;
                particle.rotation += .08 * dt;
                particle.life = Math.max(1 - (now - start) / duration, 0);
                ctx.save();
                ctx.globalAlpha = particle.life;
                ctx.translate(particle.x, particle.y);
                ctx.rotate(particle.rotation);
                ctx.fillStyle = particle.color;
                ctx.fillRect(-particle.size / 2, -particle.size / 3, particle.size, particle.size * .65);
                ctx.restore();
            });
            if (now - start < duration) frameId = requestAnimationFrame(draw);
            else ctx.clearRect(0, 0, rect.width, rect.height);
        };
        frameId = requestAnimationFrame(draw);
        return () => { cancelAnimationFrame(frameId); ctx.clearRect(0, 0, rect.width, rect.height); };
    };

    const playCelebration = (root, animation) => {
        const canvasRoot = root.matches?.("[data-twitch-goal-canvas]") ? root : root.querySelector("[data-twitch-goal-canvas]");
        const effectCanvas = root.closest?.("[data-goal-preview]")?.querySelector("[data-celebration-canvas]")
            || document.querySelector("body.twitch-goal-source > [data-celebration-canvas]")
            || root.querySelector?.("[data-celebration-canvas]");
        if (!canvasRoot) return;
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const duration = clamp(animation.duration, 1, 10) * 1000;
        canvasRoot.classList.remove("is-celebrating-neon", "is-celebrating-bounce", "is-goal-flash");
        if (reduced) {
            canvasRoot.classList.add("is-goal-flash");
        } else if (animation.type === "neon") {
            canvasRoot.classList.add("is-celebrating-neon");
        } else if (animation.type === "bounce") {
            canvasRoot.classList.add("is-celebrating-bounce");
        } else if (["confetti", "fireworks", "particles"].includes(animation.type)) {
            playParticles(effectCanvas, animation);
        }
        window.setTimeout(() => canvasRoot.classList.remove("is-celebrating-neon", "is-celebrating-bounce", "is-goal-flash"), duration);
        playSound(animation.sound, animation.volume);
    };

    const csrfToken = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const post = async (url) => {
        const response = await fetch(url, {
            method: "POST", credentials: "same-origin",
            headers: {"X-CSRFToken": csrfToken(), Accept: "application/json"},
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || "Request failed");
        return payload;
    };

    const initializeEditor = (editor) => {
        const form = editor.querySelector("[data-goal-form]");
        const canvas = editor.querySelector("[data-twitch-goal-canvas]");
        const shell = editor.querySelector("[data-goal-preview]");
        const elementsInput = form?.querySelector("[data-elements-input]");
        if (!form || !canvas || !shell || !elementsInput) return;
        let elements;
        try { elements = JSON.parse(elementsInput.value || "[]"); } catch { elements = []; }
        const sample = parseScript("twitch-goal-sample-state", {});
        const templates = parseScript("twitch-goal-layout-templates", {});
        let selectedId = elements[0]?.id || null;
        let grid = false;
        let previewMode = "sample";
        let liveState = null;
        let liveTimer = null;

        const sync = () => { elementsInput.value = JSON.stringify(elements); };
        const notify = () => { sync(); form.dispatchEvent(new CustomEvent("nexora:editor-change", {bubbles: true})); };
        const setCustom = () => { const layout = form.querySelector("#id_layout_mode"); if (layout) layout.value = "custom"; };
        const state = () => {
            const source = previewMode === "live" && liveState
                ? {...sample, goal: liveState.goal, channel: liveState.channel}
                : sample;
            const design = designFromForm(form, source);
            const target = Math.max(number(form.querySelector("#id_target_value")?.value, 1000), 1);
            const sampleCurrent = form.querySelector("#id_progress_mode")?.value === "campaign" ? 42 : Math.min(842, target);
            const goal = previewMode === "live" && liveState
                ? liveState.goal
                : {...sample.goal, current_value: sampleCurrent, target_value: target, remaining: Math.max(target - sampleCurrent, 0), progress_percent: Math.min(sampleCurrent / target * 100, 100)};
            return {...source, ...design, goal};
        };
        const renderList = () => {
            const list = editor.querySelector("[data-element-list]");
            if (!list) return;
            list.innerHTML = "";
            elements.slice().sort((a, b) => number(b.z_index) - number(a.z_index)).forEach((element) => {
                const row = document.createElement("div");
                row.className = "goal-element-list__row";
                const button = document.createElement("button");
                button.type = "button";
                button.classList.toggle("is-selected", element.id === selectedId);
                button.innerHTML = `<span>${element.type.replaceAll("_", " ")}</span><b>${element.z_index || 1}</b>`;
                button.addEventListener("click", () => { selectedId = element.id; render(); });
                const visibility = document.createElement("button");
                visibility.type = "button";
                visibility.className = "goal-element-list__visibility";
                visibility.setAttribute("aria-label", "Toggle visibility");
                visibility.setAttribute("aria-pressed", String(element.visible !== false));
                visibility.textContent = element.visible === false ? "○" : "●";
                visibility.addEventListener("click", () => {
                    element.visible = element.visible === false;
                    render(); notify();
                });
                row.append(button, visibility);
                list.append(row);
            });
        };
        const updateControls = () => {
            const controls = editor.querySelector("[data-selected-controls]");
            const selected = elements.find((item) => item.id === selectedId);
            if (!controls || !selected) { if (controls) controls.hidden = true; return; }
            controls.hidden = false;
            controls.querySelector("[data-selected-title]").textContent = selected.type.replaceAll("_", " ");
            controls.querySelectorAll("[data-element-property]").forEach((control) => {
                const value = selected[control.dataset.elementProperty];
                if (control.type === "checkbox") control.checked = value !== false;
                else control.value = value ?? "";
            });
        };
        const render = () => {
            const currentState = state();
            applyDesign(canvas, currentState);
            window.NexoraBranding?.apply(canvas, currentState);
            renderElements(canvas, elements, currentState, true, selectedId);
            renderList(); updateControls(); scalePreview(shell);
            const width = editor.querySelector("[data-preview-width]");
            const height = editor.querySelector("[data-preview-height]");
            if (width) width.textContent = String(currentState.canvas_width);
            if (height) height.textContent = String(currentState.canvas_height);
            editor.querySelectorAll("[data-source-width]").forEach((node) => node.textContent = String(currentState.canvas_width + 180));
            editor.querySelectorAll("[data-source-height]").forEach((node) => node.textContent = String(currentState.canvas_height + 240));
        };

        canvas.addEventListener("pointerdown", (event) => {
            const node = event.target.closest("[data-goal-element]");
            if (!node) return;
            const item = elements.find((candidate) => candidate.id === node.dataset.elementId);
            if (!item) return;
            selectedId = item.id;
            const resizing = Boolean(event.target.closest("[data-resize-handle]"));
            const start = {x: event.clientX, y: event.clientY, left: item.x, top: item.y, width: item.width, height: item.height};
            let changed = false;
            const move = (moveEvent) => {
                const scale = canvas._goalScale || 1;
                const dx = (moveEvent.clientX - start.x) / scale;
                const dy = (moveEvent.clientY - start.y) / scale;
                if (resizing) {
                    item.width = Math.max(20, Math.round((start.width + dx) / (grid ? 10 : 1)) * (grid ? 10 : 1));
                    item.height = Math.max(16, Math.round((start.height + dy) / (grid ? 10 : 1)) * (grid ? 10 : 1));
                } else {
                    item.x = Math.max(0, Math.round((start.left + dx) / (grid ? 10 : 1)) * (grid ? 10 : 1));
                    item.y = Math.max(0, Math.round((start.top + dy) / (grid ? 10 : 1)) * (grid ? 10 : 1));
                }
                changed = true; setCustom(); render();
            };
            const end = () => {
                window.removeEventListener("pointermove", move);
                if (changed) notify();
            };
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", end, {once: true});
            event.preventDefault(); render();
        });

        canvas.addEventListener("keydown", (event) => {
            const node = event.target.closest("[data-goal-element]");
            const item = elements.find((candidate) => candidate.id === node?.dataset.elementId);
            if (!item) return;
            if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
                const step = event.shiftKey || grid ? 10 : 1;
                if (event.key === "ArrowLeft") item.x = Math.max(0, number(item.x) - step);
                if (event.key === "ArrowRight") item.x = number(item.x) + step;
                if (event.key === "ArrowUp") item.y = Math.max(0, number(item.y) - step);
                if (event.key === "ArrowDown") item.y = number(item.y) + step;
                event.preventDefault(); setCustom(); render(); notify();
            }
            if (event.key === "Delete") {
                elements = elements.filter((candidate) => candidate.id !== item.id);
                selectedId = elements[0]?.id || null;
                event.preventDefault(); setCustom(); render(); notify();
            }
        });

        editor.querySelectorAll("[data-element-property]").forEach((control) => control.addEventListener("input", () => {
            const item = elements.find((candidate) => candidate.id === selectedId);
            if (!item) return;
            const property = control.dataset.elementProperty;
            item[property] = control.type === "checkbox"
                ? control.checked
                : ["color", "background_color", "text_align"].includes(property)
                    ? control.value
                    : number(control.value);
            setCustom(); render(); notify();
        }));
        editor.querySelector("[data-delete-element]")?.addEventListener("click", () => {
            elements = elements.filter((item) => item.id !== selectedId);
            selectedId = elements[0]?.id || null; setCustom(); render(); notify();
        });
        editor.querySelector("[data-layer-up]")?.addEventListener("click", () => {
            const item = elements.find((candidate) => candidate.id === selectedId); if (!item) return;
            item.z_index = clamp(number(item.z_index, 1) + 1, 0, 100); setCustom(); render(); notify();
        });
        editor.querySelector("[data-layer-down]")?.addEventListener("click", () => {
            const item = elements.find((candidate) => candidate.id === selectedId); if (!item) return;
            item.z_index = clamp(number(item.z_index, 1) - 1, 0, 100); setCustom(); render(); notify();
        });
        editor.querySelectorAll("[data-add-element]").forEach((button) => button.addEventListener("click", () => {
            const type = button.dataset.addElement;
            let index = 1; while (elements.some((item) => item.id === `${type}-${index}`)) index += 1;
            const item = {id: `${type}-${index}`, type, x: 30, y: 30, width: type.includes("progress") ? 300 : 180, height: type === "progress_ring" ? 180 : 44, font_size: 20, font_weight: 700, color: "#ffffff", background_color: "#2c2440", border_radius: 12, text_align: "left", z_index: elements.length + 1, visible: true, stroke_width: 9};
            elements.push(item); selectedId = item.id; setCustom(); render(); notify();
        }));
        const applyLayout = (layout) => {
            if (!templates[layout]) return;
            elements = clone(templates[layout]); selectedId = elements[0]?.id || null;
            const dimensions = {horizontal: [900,160], compact: [720,110], card: [480,320], radial: [420,420]}[layout];
            form.querySelector("#id_layout_mode").value = layout;
            form.querySelector("#id_canvas_width").value = dimensions[0];
            form.querySelector("#id_canvas_height").value = dimensions[1];
            render(); notify();
        };
        editor.querySelectorAll("[data-apply-layout]").forEach((button) => button.addEventListener("click", () => applyLayout(button.dataset.applyLayout)));
        form.querySelector("#id_layout_mode")?.addEventListener("change", (event) => { if (event.target.value !== "custom") applyLayout(event.target.value); });
        editor.querySelector("[data-grid-toggle]")?.addEventListener("change", (event) => { grid = event.target.checked; });

        const loadLive = async () => {
            if (!editor.dataset.stateUrl || previewMode !== "live") return;
            const status = editor.querySelector("[data-preview-status]");
            try {
                const response = await fetch(editor.dataset.stateUrl, {credentials: "same-origin", cache: "no-store", headers: {Accept: "application/json"}});
                if (!response.ok) throw new Error("Live data unavailable");
                liveState = await response.json();
                if (status) status.textContent = liveState.goal?.status || "live";
                render();
            } catch {
                if (status) status.textContent = "unavailable";
            }
        };
        editor.querySelectorAll("[data-preview-mode]").forEach((button) => button.addEventListener("click", () => {
            previewMode = button.dataset.previewMode;
            editor.querySelectorAll("[data-preview-mode]").forEach((candidate) => candidate.classList.toggle("is-active", candidate === button));
            window.clearInterval(liveTimer);
            liveTimer = null;
            if (previewMode === "live") {
                loadLive();
                liveTimer = window.setInterval(loadLive, 2000);
            } else {
                const status = editor.querySelector("[data-preview-status]");
                if (status) status.textContent = "";
                render();
            }
        }));

        form.addEventListener("input", (event) => { if (!event.target.matches("[data-element-property]")) render(); });
        form.addEventListener("change", () => {
            editor.querySelector("[data-subscription-metric-field]").hidden = form.querySelector("#id_goal_type")?.value !== "subscriptions";
            const reset = editor.querySelector("[data-campaign-reset-container]");
            if (reset) reset.hidden = form.querySelector("#id_progress_mode")?.value !== "campaign";
            render();
        });
        form.addEventListener("nexora:editor-restore", () => { try { elements = JSON.parse(elementsInput.value || "[]"); } catch { elements = []; } selectedId = elements[0]?.id || null; render(); });
        form.addEventListener("submit", sync);
        editor.querySelector("[data-test-celebration]")?.addEventListener("click", () => playCelebration(shell, {
            type: form.querySelector("#id_animation_type")?.value,
            duration: number(form.querySelector("#id_animation_duration")?.value, 5),
            intensity: form.querySelector("#id_animation_intensity")?.value,
            primary_color: form.querySelector("#id_animation_primary_color")?.value,
            secondary_color: form.querySelector("#id_animation_secondary_color")?.value,
            sound: form.querySelector("#id_sound_type")?.value,
            volume: number(form.querySelector("#id_sound_volume")?.value, 70),
        }));
        editor.querySelector("[data-replay-obs]")?.addEventListener("click", async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            const safetyTimer = window.setTimeout(() => { button.disabled = false; }, 2500);
            try { await post(button.dataset.replayUrl); }
            finally { window.clearTimeout(safetyTimer); button.disabled = false; }
        });
        editor.querySelector("[data-campaign-reset]")?.addEventListener("click", async (event) => { event.currentTarget.disabled = true; try { await post(event.currentTarget.dataset.campaignResetUrl); location.reload(); } catch (error) { window.alert(error.message); event.currentTarget.disabled = false; } });
        editor.querySelector("[data-subscription-metric-field]").hidden = form.querySelector("#id_goal_type")?.value !== "subscriptions";
        const campaignReset = editor.querySelector("[data-campaign-reset-container]");
        if (campaignReset) campaignReset.hidden = form.querySelector("#id_progress_mode")?.value !== "campaign";
        render();
        if (window.ResizeObserver) new ResizeObserver(() => scalePreview(shell)).observe(shell);
        else window.addEventListener("resize", () => scalePreview(shell));
    };

    const initializePublic = (body) => {
        const canvas = body.querySelector("[data-twitch-goal-canvas]");
        const stateUrl = body.dataset.stateUrl;
        if (!canvas || !stateUrl) return;
        let lastSequence = number(body.dataset.initialSequence, 0);
        const applyState = (state) => {
            applyDesign(canvas, state);
            window.NexoraBranding?.apply(canvas, state);
            renderElements(canvas, state.elements || [], state, false);
            const nextSequence = number(state.celebration_sequence, 0);
            if (nextSequence > lastSequence) playCelebration(body, state.animation || {});
            lastSequence = nextSequence;
        };
        applyState(parseScript("twitch-goal-state", {}));
        window.NexoraPolling?.start({url: stateUrl, interval: 2000, hiddenInterval: 10000, onData: applyState});
        scalePublic(body);
        window.addEventListener("resize", () => scalePublic(body));
    };

    const copyText = async (value) => {
        if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
        const area = document.createElement("textarea"); area.value = value; document.body.append(area); area.select(); document.execCommand("copy"); area.remove();
    };
    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-copy-url]"); if (!button) return;
        try { await copyText(button.dataset.copyUrl); const toast = document.querySelector("[data-copy-toast]"); if (toast) { toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 2200); } } catch { /* readonly URL remains available */ }
    });
    document.addEventListener("submit", (event) => {
        const message = event.target.dataset.confirmMessage || event.target.dataset.confirmAction;
        if (message && !window.confirm(message)) event.preventDefault();
    });

    document.querySelectorAll("[data-twitch-goal-editor]").forEach(initializeEditor);
    const body = document.querySelector("[data-twitch-goal-source]"); if (body) initializePublic(body);
    window.NexoraGoalCelebration = {play: playCelebration};
})();
