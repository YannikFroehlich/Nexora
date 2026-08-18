(() => {
    const number = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);
    const resizeDirections = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
    const sourceExtraWidth = 80;
    const sourceExtraHeight = 96;
    const layoutModes = Object.freeze({
        duel: "broadcast_duel",
        list: "broadcast_list",
        custom: "custom",
    });
    const iconPaths = Object.freeze({
        minus: ["M5 12h14"],
        plus: ["M12 5v14", "M5 12h14"],
        reset: ["M3 12a9 9 0 1 0 3-6.7", "M3 5v6h6"],
        save: ["M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z", "M17 21v-8H7v8", "M7 3v5h8"],
        delete: ["M3 6h18", "M8 6V4h8v2", "M19 6l-1 14H6L5 6", "M10 11v6", "M14 11v6"],
    });

    const defaultState = () => ({
        name: "Score HUD",
        layout_mode: layoutModes.duel,
        canvas_width: 960,
        canvas_height: 200,
        background_color: "#0f172a",
        background_opacity: 0,
        border_color: "#38bdf8",
        border_width: 0,
        corner_radius: 0,
        elements: [],
        layout_templates: {},
        participants: [
            {id: "slot-1", name: "Player 1", score: 0, accent_color: "#38bdf8", initials: "P1", image_url: ""},
            {id: "slot-2", name: "Player 2", score: 0, accent_color: "#fb7185", initials: "P2", image_url: ""},
        ],
    });

    const readInitialState = () => {
        const node = document.getElementById("score-state");
        if (!node) return defaultState();
        try {
            const state = JSON.parse(node.textContent);
            return {
                ...defaultState(),
                ...state,
                participants: state.participants?.length ? state.participants : defaultState().participants,
                elements: state.elements?.length ? state.elements : [],
            };
        } catch {
            return defaultState();
        }
    };

    const normalizeLayoutMode = (mode) => {
        if (mode === "duel") return layoutModes.duel;
        if (mode === "list") return layoutModes.list;
        return Object.values(layoutModes).includes(mode) ? mode : layoutModes.custom;
    };

    const hexToRgba = (hex, opacity) => {
        const normalized = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : "#0f172a";
        const red = Number.parseInt(normalized.slice(1, 3), 16);
        const green = Number.parseInt(normalized.slice(3, 5), 16);
        const blue = Number.parseInt(normalized.slice(5, 7), 16);
        return `rgba(${red}, ${green}, ${blue}, ${clamp(number(opacity, 0), 0, 100) / 100})`;
    };

    const participantMap = (participants) => new Map(participants.map((participant) => [
        String(participant.id),
        participant,
    ]));

    const elementLabel = (element, participants) => {
        const participant = participantMap(participants).get(String(element.participant_id));
        const typeLabels = {
            participant_image: "Image",
            participant_name: "Name",
            participant_score: "Score",
        };
        return `${participant?.name || "Participant"} - ${typeLabels[element.type] || element.type}`;
    };

    const createIcon = (iconName) => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.classList.add("score-icon-button__icon");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");
        (iconPaths[iconName] || []).forEach((pathData) => {
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", pathData);
            svg.append(path);
        });
        return svg;
    };

    const createElementContent = (node, element, participant) => {
        if (element.type === "participant_image") {
            if (participant?.image_url) {
                const image = document.createElement("img");
                image.alt = "";
                image.src = participant.image_url;
                node.append(image);
            } else {
                const initials = document.createElement("span");
                initials.className = "score-overlay-element__text";
                initials.textContent = participant?.initials || "?";
                node.append(initials);
            }
            return;
        }

        const text = document.createElement("span");
        text.className = "score-overlay-element__text";
        text.textContent = element.type === "participant_score"
            ? String(participant?.score ?? 0)
            : (participant?.name || "");
        node.append(text);
    };

    const scoreFontSize = (baseSize, score) => {
        const base = number(baseSize, 42);
        const length = String(score ?? 0).length;
        return clamp(base - Math.max(length - 3, 0) * 6, 24, base);
    };

    const renderElements = (
        canvas,
        elements,
        participants,
        editor = false,
        selectedId = null,
        changedParticipantIds = new Set(),
    ) => {
        const participantsById = participantMap(participants);
        const layer = canvas.querySelector("[data-score-elements-layer]") || canvas;
        layer.replaceChildren();

        elements.forEach((element) => {
            const participant = participantsById.get(String(element.participant_id));
            if (!participant) return;

            const node = document.createElement("div");
            node.className = `score-overlay-element score-overlay-element--${element.type}`;
            if (
                element.type === "participant_score"
                && changedParticipantIds.has(String(participant.id))
            ) {
                node.classList.add("is-score-updated");
            }
            node.dataset.scoreElement = "";
            node.dataset.elementId = element.id;
            node.dataset.elementType = element.type;
            node.dataset.participantId = String(participant.id);
            node.dataset.textAlign = element.text_align || "center";
            node.style.left = `${element.x}px`;
            node.style.top = `${element.y}px`;
            node.style.width = `${element.width}px`;
            node.style.height = `${element.height}px`;
            node.style.color = element.color;
            node.style.backgroundColor = element.background_color;
            node.style.setProperty("--score-element-background", element.background_color);
            node.style.fontSize = `${element.type === "participant_score"
                ? scoreFontSize(element.font_size, participant.score)
                : element.font_size}px`;
            node.style.borderRadius = `${element.border_radius}px`;
            node.style.textAlign = element.text_align || "center";
            node.style.justifyContent = {
                left: "flex-start",
                center: "center",
                right: "flex-end",
            }[element.text_align || "center"];
            node.style.setProperty("--score-participant-accent", participant.accent_color || element.background_color);

            if (editor) {
                node.tabIndex = 0;
                node.setAttribute("role", "button");
                node.setAttribute("aria-label", elementLabel(element, participants));
                node.classList.toggle("is-selected", element.id === selectedId);
            }

            createElementContent(node, element, participant);

            if (editor && element.id === selectedId) {
                resizeDirections.forEach((direction) => {
                    const handle = document.createElement("span");
                    handle.className = `score-resize-handle score-resize-handle--${direction}`;
                    handle.dataset.resizeHandle = direction;
                    handle.setAttribute("aria-hidden", "true");
                    node.append(handle);
                });
            }

            layer.append(node);
        });
    };

    const applyCanvasDesign = (canvas, design) => {
        canvas.dataset.scoreLayoutMode = normalizeLayoutMode(design.layout_mode);
        canvas.style.setProperty("--score-canvas-width", `${number(design.canvas_width, 960)}px`);
        canvas.style.setProperty("--score-canvas-height", `${number(design.canvas_height, 200)}px`);
        canvas.style.setProperty(
            "--score-canvas-background",
            design.background_rgba || hexToRgba(design.background_color, design.background_opacity),
        );
        canvas.style.setProperty("--score-canvas-border-color", design.border_color || "#38bdf8");
        canvas.style.setProperty("--score-canvas-border-width", `${clamp(number(design.border_width), 0, 24)}px`);
        canvas.style.setProperty("--score-canvas-radius", `${clamp(number(design.corner_radius, 28), 0, 80)}px`);
    };

    const scalePreview = (shell) => {
        const canvas = shell.querySelector("[data-score-canvas]");
        if (!canvas || shell.closest(".score-overlay-source")) return;

        const width = number(getComputedStyle(canvas).getPropertyValue("--score-canvas-width"), canvas.offsetWidth);
        const height = number(getComputedStyle(canvas).getPropertyValue("--score-canvas-height"), canvas.offsetHeight);
        const padding = 26;
        const availableWidth = Math.max(shell.clientWidth - (padding * 2), 1);
        const maxPreviewHeight = clamp(window.innerHeight - 430, 360, 680);
        const scale = Math.min(availableWidth / width, maxPreviewHeight / height, 1);
        const renderedWidth = width * scale;
        const renderedHeight = height * scale;

        canvas.style.left = `${Math.max((shell.clientWidth - renderedWidth) / 2, 0)}px`;
        canvas.style.top = `${padding}px`;
        canvas.style.transform = `scale(${scale})`;
        canvas.style.setProperty("--score-preview-scale", scale.toFixed(4));
        const inverseScale = 1 / Math.max(scale, 0.01);
        canvas.style.setProperty("--score-handle-size", `${15 * inverseScale}px`);
        canvas.style.setProperty("--score-handle-offset", `${-12 * inverseScale}px`);
        canvas.style.setProperty("--score-handle-corner-offset", `${-12 * inverseScale}px`);
        canvas.style.setProperty("--score-handle-border-width", `${2 * inverseScale}px`);
        canvas.style.setProperty("--score-outline-width", `${2 * inverseScale}px`);
        canvas.style.setProperty("--score-outline-offset", `${3 * inverseScale}px`);
        canvas.style.setProperty("--score-outline-glow", `${7 * inverseScale}px`);
        canvas.style.setProperty("--score-handle-shadow-y", `${2 * inverseScale}px`);
        canvas.style.setProperty("--score-handle-shadow-blur", `${7 * inverseScale}px`);
        canvas._scoreScale = scale;
        shell.style.height = `${renderedHeight + (padding * 2)}px`;
    };

    const scaleAllPreviews = () => {
        document.querySelectorAll("[data-score-scale-shell]").forEach(scalePreview);
    };

    const getCsrfToken = () => (
        document.querySelector("[name=csrfmiddlewaretoken]")?.value
        || document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1]
        || ""
    );

    const postForm = async (url, data) => {
        const body = new URLSearchParams();
        Object.entries(data).forEach(([key, value]) => body.append(key, value ?? ""));
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const errors = payload.errors
                ? Object.entries(payload.errors).map(([field, fieldErrors]) => `${field}: ${fieldErrors.map((item) => item.message || item).join(", ")}`).join("\n")
                : "";
            throw new Error(payload.error || errors || "Request failed");
        }
        return payload;
    };

    const copyText = async (text) => {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }
        const input = document.createElement("textarea");
        input.value = text;
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.append(input);
        input.select();
        document.execCommand("copy");
        input.remove();
    };

    const initializeEditor = (editor) => {
        const form = editor.querySelector("[data-score-form]");
        const elementsInput = editor.querySelector("[data-elements-input]");
        const layoutModeInput = editor.querySelector("[data-layout-mode-input]");
        const canvas = editor.querySelector("[data-score-canvas]");
        const list = editor.querySelector("[data-element-list]");
        const count = editor.querySelector("[data-element-count]");
        const controls = editor.querySelector("[data-selected-controls]");
        const empty = editor.querySelector("[data-selected-empty]");
        const selectedTitle = editor.querySelector("[data-selected-element-title]");
        const participantList = editor.querySelector("[data-participant-list]");
        const widthInput = editor.querySelector("#id_canvas_width");
        const heightInput = editor.querySelector("#id_canvas_height");
        const backgroundInput = editor.querySelector("#id_background_color");
        const opacityInput = editor.querySelector("#id_background_opacity");
        const borderColorInput = editor.querySelector("#id_border_color");
        const borderWidthInput = editor.querySelector("#id_border_width");
        const radiusInput = editor.querySelector("#id_corner_radius");
        const previewWidth = editor.querySelector("[data-preview-width]");
        const previewHeight = editor.querySelector("[data-preview-height]");
        const sourceWidths = editor.querySelectorAll("[data-source-width]");
        const sourceHeights = editor.querySelectorAll("[data-source-height]");
        const gridToggle = editor.querySelector("[data-grid-toggle]");
        const gridSizeInput = editor.querySelector("[data-grid-size]");
        const emptySelectedTitle = selectedTitle?.textContent || "";

        if (!form || !elementsInput || !canvas) return;

        let state = readInitialState();
        let elements;
        try {
            elements = JSON.parse(elementsInput.value || "[]");
        } catch {
            elements = [];
        }
        if (!elements.length) elements = state.elements || [];
        let participants = state.participants || defaultState().participants;
        let selectedId = elements[0]?.id || null;
        let layoutMode = normalizeLayoutMode(layoutModeInput?.value || state.layout_mode || layoutModes.duel);
        let gridEnabled = false;
        let gridSize = 10;

        const cloneElements = (items = []) => items.map((item) => ({...item}));
        const templateFor = (mode) => state.layout_templates?.[normalizeLayoutMode(mode)] || null;
        if (!elements.length && templateFor(layoutMode)) {
            elements = cloneElements(templateFor(layoutMode).elements || []);
            selectedId = elements[0]?.id || null;
        }

        const design = () => ({
            layout_mode: layoutMode,
            canvas_width: clamp(number(widthInput.value, 960), 320, 1920),
            canvas_height: clamp(number(heightInput.value, 200), 140, 1080),
            background_color: backgroundInput.value || "#0f172a",
            background_opacity: clamp(number(opacityInput.value, 0), 0, 100),
            border_color: borderColorInput.value || "#38bdf8",
            border_width: clamp(number(borderWidthInput.value), 0, 24),
            corner_radius: clamp(number(radiusInput.value, 0), 0, 80),
        });

        const selectedElement = () => elements.find((element) => element.id === selectedId) || null;
        const notifyEditorChange = () => form.dispatchEvent(new CustomEvent("nexora:editor-change", {bubbles: true}));
        const syncElements = () => {
            elementsInput.value = JSON.stringify(elements);
            if (layoutModeInput) layoutModeInput.value = layoutMode;
        };
        const setCustomLayout = () => {
            if (layoutMode !== layoutModes.custom) {
                layoutMode = layoutModes.custom;
                syncElements();
            }
        };
        const snapToGrid = (value) => gridEnabled
            ? Math.round(value / gridSize) * gridSize
            : Math.round(value);

        const fitElementToCanvas = (element) => {
            const currentDesign = design();
            element.width = clamp(number(element.width, 120), 24, currentDesign.canvas_width);
            element.height = clamp(number(element.height, 32), 8, currentDesign.canvas_height);
            element.x = clamp(number(element.x), 0, Math.max(currentDesign.canvas_width - element.width, 0));
            element.y = clamp(number(element.y), 0, Math.max(currentDesign.canvas_height - element.height, 0));
        };

        const applyGridState = () => {
            if (!gridToggle || !gridSizeInput) return;
            gridToggle.checked = gridEnabled;
            gridSizeInput.value = String(gridSize);
            gridSizeInput.disabled = !gridEnabled;
            canvas.classList.toggle("is-grid-enabled", gridEnabled);
            canvas.style.setProperty("--score-grid-size", `${gridSize}px`);
        };

        const ensureParticipantElements = () => {
            if (layoutMode !== layoutModes.custom) return;
            participants.forEach((participant, index) => {
                const existingTypes = new Set(
                    elements
                        .filter((element) => String(element.participant_id) === String(participant.id))
                        .map((element) => element.type),
                );
                const y = 24 + (index * 64);
                const defaults = [
                    {
                        id: `participant-${participant.id}-image`,
                        type: "participant_image",
                        x: 26,
                        y,
                        width: 50,
                        height: 50,
                        font_size: 20,
                        color: "#ffffff",
                        background_color: participant.accent_color,
                        border_radius: 14,
                        text_align: "center",
                    },
                    {
                        id: `participant-${participant.id}-name`,
                        type: "participant_name",
                        x: 90,
                        y: y + 7,
                        width: 420,
                        height: 30,
                        font_size: 22,
                        color: "#ffffff",
                        background_color: "#111827",
                        border_radius: 8,
                        text_align: "left",
                    },
                    {
                        id: `participant-${participant.id}-score`,
                        type: "participant_score",
                        x: 520,
                        y,
                        width: 110,
                        height: 50,
                        font_size: 38,
                        color: "#ffffff",
                        background_color: participant.accent_color,
                        border_radius: 14,
                        text_align: "center",
                    },
                ];
                defaults.forEach((element) => {
                    if (!existingTypes.has(element.type)) {
                        elements.push({...element, participant_id: String(participant.id)});
                    }
                });
            });
        };

        const applyLayout = (mode) => {
            let nextMode = normalizeLayoutMode(mode);
            if (nextMode === layoutModes.duel && participants.length !== 2) {
                nextMode = layoutModes.list;
            }
            const template = templateFor(nextMode);
            if (!template) return;
            if (
                layoutMode === layoutModes.custom
                && !window.confirm(editor.dataset.scorePresetConfirm || "Replace custom layout?")
            ) {
                return;
            }

            layoutMode = nextMode;
            elements = cloneElements(template.elements || []);
            selectedId = elements[0]?.id || null;
            if (widthInput) widthInput.value = template.canvas_width ?? 960;
            if (heightInput) heightInput.value = template.canvas_height ?? 200;
            if (backgroundInput) backgroundInput.value = template.background_color || "#0f172a";
            if (opacityInput) opacityInput.value = template.background_opacity ?? 0;
            if (borderColorInput) borderColorInput.value = template.border_color || "#38bdf8";
            if (borderWidthInput) borderWidthInput.value = template.border_width ?? 0;
            if (radiusInput) radiusInput.value = template.corner_radius ?? 0;
            selectedId = elements[0]?.id || null;
            render();
            notifyEditorChange();
        };

        const updateSelectedControls = () => {
            const element = selectedElement();
            if (!controls || !empty || !selectedTitle) return;
            controls.hidden = !element;
            empty.hidden = Boolean(element);
            selectedTitle.textContent = element ? elementLabel(element, participants) : emptySelectedTitle;
            if (!element) return;

            editor.querySelectorAll("[data-element-property]").forEach((input) => {
                input.value = element[input.dataset.elementProperty];
            });
        };

        const renderList = () => {
            if (!list || !count) return;
            list.replaceChildren();
            count.textContent = elements.length;
            elements.forEach((element) => {
                const button = document.createElement("button");
                const label = document.createElement("span");
                const position = document.createElement("span");
                button.type = "button";
                button.className = "score-element-list__item";
                button.dataset.selectElement = element.id;
                button.classList.toggle("is-selected", element.id === selectedId);
                label.textContent = elementLabel(element, participants);
                position.textContent = `${element.x} / ${element.y}`;
                button.append(label, position);
                list.append(button);
            });
        };

        const renderParticipants = () => {
            if (!participantList) return;
            participantList.replaceChildren();
            participants.forEach((participant) => {
                const row = document.createElement("article");
                row.className = "score-participant-row";
                row.dataset.participantRow = participant.id;

                const badge = document.createElement("span");
                badge.className = "score-participant-row__badge";
                badge.style.backgroundColor = participant.accent_color;
                badge.textContent = participant.initials || "?";

                const formWrap = document.createElement("div");
                formWrap.className = "score-participant-row__fields";
                formWrap.innerHTML = `
                    <input class="form-control" name="name" value="">
                    <input class="color-control" name="accent_color" type="color" value="">
                    <select class="form-control" name="image_asset"></select>
                `;
                formWrap.querySelector("[name=name]").value = participant.name;
                formWrap.querySelector("[name=accent_color]").value = participant.accent_color || "#38bdf8";

                const imageSelect = formWrap.querySelector("[name=image_asset]");
                const sourceSelect = editor.querySelector("#id_image_asset");
                if (sourceSelect) {
                    sourceSelect.querySelectorAll("option").forEach((option) => {
                        imageSelect.append(option.cloneNode(true));
                    });
                }
                if (participant.image_url) {
                    const matchingOption = Array.from(imageSelect.options)
                        .find((option) => option.dataset.assetUrl === participant.image_url);
                    if (matchingOption) imageSelect.value = matchingOption.value;
                }

                const score = document.createElement("strong");
                score.className = "score-participant-row__score";
                score.textContent = participant.score;

                const actions = document.createElement("div");
                actions.className = "score-participant-row__actions";
                [
                    ["-1", "minus", participantList.dataset.minusLabel, "minus"],
                    ["+1", "plus", participantList.dataset.plusLabel, "plus"],
                    ["reset", "reset", participantList.dataset.resetLabel],
                    ["save", "save", participantList.dataset.saveLabel],
                    ["delete", "delete", participantList.dataset.deleteLabel],
                ].forEach(([action, className, label, iconName]) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = `score-icon-button score-icon-button--${className}`;
                    button.dataset.participantAction = action;
                    button.append(createIcon(iconName || className));
                    button.setAttribute("aria-label", label || action);
                    button.title = label || action;
                    actions.append(button);
                });

                row.append(badge, formWrap, score, actions);
                participantList.append(row);
            });
        };

        const applyReturnedState = (nextState) => {
            if (!nextState) return;
            state = {...state, ...nextState};
            participants = nextState.participants || participants;
            elements = nextState.elements ? cloneElements(nextState.elements) : elements;
            layoutMode = normalizeLayoutMode(nextState.layout_mode || layoutMode);
            if (widthInput && nextState.canvas_width) widthInput.value = nextState.canvas_width;
            if (heightInput && nextState.canvas_height) heightInput.value = nextState.canvas_height;
            if (backgroundInput && nextState.background_color) {
                backgroundInput.value = nextState.background_color;
            }
            if (opacityInput && nextState.background_opacity !== undefined) {
                opacityInput.value = nextState.background_opacity;
            }
            if (borderColorInput && nextState.border_color) {
                borderColorInput.value = nextState.border_color;
            }
            if (borderWidthInput && nextState.border_width !== undefined) {
                borderWidthInput.value = nextState.border_width;
            }
            if (radiusInput && nextState.corner_radius !== undefined) {
                radiusInput.value = nextState.corner_radius;
            }
            selectedId = elements.some((element) => element.id === selectedId)
                ? selectedId
                : elements[0]?.id || null;
        };

        const render = () => {
            ensureParticipantElements();
            const currentDesign = design();
            elements.forEach(fitElementToCanvas);
            applyCanvasDesign(canvas, currentDesign);
            applyGridState();
            renderElements(canvas, elements, participants, true, selectedId);
            renderList();
            renderParticipants();
            updateSelectedControls();
            syncElements();
            if (previewWidth) previewWidth.textContent = currentDesign.canvas_width;
            if (previewHeight) previewHeight.textContent = currentDesign.canvas_height;
            sourceWidths.forEach((node) => { node.textContent = currentDesign.canvas_width + sourceExtraWidth; });
            sourceHeights.forEach((node) => { node.textContent = currentDesign.canvas_height + sourceExtraHeight; });
            requestAnimationFrame(scaleAllPreviews);
        };

        const select = (elementId, focus = false) => {
            selectedId = elementId;
            render();
            if (focus) {
                Array.from(canvas.querySelectorAll("[data-score-element]"))
                    .find((node) => node.dataset.elementId === elementId)
                    ?.focus();
            }
        };

        editor.addEventListener("click", async (event) => {
            const listButton = event.target.closest("[data-select-element]");
            const layoutButton = event.target.closest("[data-layout-template]");
            const copyButton = event.target.closest("[data-copy-url]");
            const addButton = event.target.closest("[data-add-participant]");
            const participantButton = event.target.closest("[data-participant-action]");
            const resetAllButton = event.target.closest("[data-reset-all]");

            if (listButton) {
                select(listButton.dataset.selectElement, true);
                return;
            }

            if (layoutButton) {
                applyLayout(layoutButton.dataset.layoutTemplate);
                return;
            }

            if (copyButton) {
                await copyText(copyButton.dataset.copyUrl);
                const toast = document.querySelector("[data-copy-toast]");
                if (toast) {
                    toast.hidden = false;
                    window.setTimeout(() => { toast.hidden = true; }, 2200);
                }
                return;
            }

            if (addButton) {
                const wrap = editor.querySelector("[data-participant-add-form]");
                if (!wrap?.dataset.action) return;
                try {
                    const nextState = await postForm(wrap.dataset.action, {
                        name: wrap.querySelector("[name=name]")?.value.trim(),
                        accent_color: wrap.querySelector("[name=accent_color]")?.value,
                        image_asset: wrap.querySelector("[name=image_asset]")?.value,
                    });
                    applyReturnedState(nextState);
                    wrap.querySelector("[name=name]").value = "";
                    render();
                } catch (error) {
                    window.alert(error.message);
                }
                return;
            }

            if (participantButton) {
                const row = participantButton.closest("[data-participant-row]");
                const participantId = row?.dataset.participantRow;
                const participant = participants.find((item) => String(item.id) === participantId);
                if (!participant) return;

                const templateUrl = (template) => (
                    template || ""
                ).replace("00000000-0000-0000-0000-000000000000", participantId);

                try {
                    let nextState = null;
                    if (participantButton.dataset.participantAction === "+1") {
                        nextState = await postForm(templateUrl(editor.dataset.scoreScoreTemplate), {delta: 1});
                    } else if (participantButton.dataset.participantAction === "-1") {
                        nextState = await postForm(templateUrl(editor.dataset.scoreScoreTemplate), {delta: -1});
                    } else if (participantButton.dataset.participantAction === "reset") {
                        nextState = await postForm(templateUrl(editor.dataset.scoreResetTemplate), {});
                    } else if (participantButton.dataset.participantAction === "save") {
                        nextState = await postForm(templateUrl(editor.dataset.scoreUpdateTemplate), {
                            name: row.querySelector("[name=name]")?.value.trim(),
                            accent_color: row.querySelector("[name=accent_color]")?.value,
                            image_asset: row.querySelector("[name=image_asset]")?.value,
                        });
                    } else if (participantButton.dataset.participantAction === "delete") {
                        if (!window.confirm(participantList.dataset.deleteConfirm || "Delete participant?")) return;
                        nextState = await postForm(templateUrl(editor.dataset.scoreDeleteTemplate), {});
                    }
                    if (nextState) {
                        applyReturnedState(nextState);
                        render();
                    }
                } catch (error) {
                    window.alert(error.message);
                }
                return;
            }

            if (resetAllButton && editor.dataset.scoreResetAllUrl) {
                try {
                    const nextState = await postForm(editor.dataset.scoreResetAllUrl, {});
                    applyReturnedState(nextState);
                    render();
                } catch (error) {
                    window.alert(error.message);
                }
            }
        });

        editor.querySelectorAll("[data-element-property]").forEach((input) => {
            input.addEventListener("input", () => {
                const element = selectedElement();
                if (!element) return;
                setCustomLayout();
                const property = input.dataset.elementProperty;
                element[property] = input.type === "color" || input.tagName === "SELECT"
                    ? input.value
                    : number(input.value, element[property]);
                fitElementToCanvas(element);
                applyCanvasDesign(canvas, design());
                renderElements(canvas, elements, participants, true, selectedId);
                renderList();
                syncElements();
            });
            input.addEventListener("change", notifyEditorChange);
        });

        [widthInput, heightInput, backgroundInput, opacityInput, borderColorInput, borderWidthInput, radiusInput]
            .forEach((input) => {
                input?.addEventListener("input", () => {
                    if (input === widthInput || input === heightInput) setCustomLayout();
                    render();
                    notifyEditorChange();
                });
            });

        ["player_one_name", "player_two_name"].forEach((name, index) => {
            const input = editor.querySelector(`[name=${name}]`);
            input?.addEventListener("input", () => {
                participants[index].name = input.value.trim() || `Player ${index + 1}`;
                participants[index].initials = participants[index].name.slice(0, 2).toUpperCase();
                render();
            });
        });

        gridToggle?.addEventListener("change", () => {
            gridEnabled = gridToggle.checked;
            applyGridState();
        });
        gridSizeInput?.addEventListener("change", () => {
            gridSize = [5, 10, 20, 40].includes(number(gridSizeInput.value))
                ? number(gridSizeInput.value)
                : 10;
            applyGridState();
        });

        canvas.addEventListener("click", (event) => {
            const node = event.target.closest("[data-score-element]");
            if (node) select(node.dataset.elementId, true);
        });

        canvas.addEventListener("keydown", (event) => {
            const node = event.target.closest("[data-score-element]");
            if (!node || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault();
            selectedId = node.dataset.elementId;
            const element = selectedElement();
            const step = gridEnabled ? gridSize * (event.shiftKey ? 5 : 1) : (event.shiftKey ? 10 : 1);
            if (event.key === "ArrowLeft") element.x -= step;
            if (event.key === "ArrowRight") element.x += step;
            if (event.key === "ArrowUp") element.y -= step;
            if (event.key === "ArrowDown") element.y += step;
            setCustomLayout();
            fitElementToCanvas(element);
            render();
            notifyEditorChange();
        });

        canvas.addEventListener("pointerdown", (event) => {
            const node = event.target.closest("[data-score-element]");
            if (!node || event.button !== 0) return;
            event.preventDefault();
            selectedId = node.dataset.elementId;
            const element = selectedElement();
            const resizeHandle = event.target.closest("[data-resize-handle]");
            const resizeDirection = resizeHandle?.dataset.resizeHandle || "";
            const startX = event.clientX;
            const startY = event.clientY;
            const originX = element.x;
            const originY = element.y;
            const originWidth = element.width;
            const originHeight = element.height;
            const originRight = originX + originWidth;
            const originBottom = originY + originHeight;
            const currentDesign = design();
            const scale = canvas._scoreScale || 1;
            let changed = false;

            node.focus({preventScroll: true});

            const move = (moveEvent) => {
                const deltaX = Math.round((moveEvent.clientX - startX) / scale);
                const deltaY = Math.round((moveEvent.clientY - startY) / scale);
                if (deltaX || deltaY) changed = true;

                if (resizeDirection) {
                    if (resizeDirection.includes("e")) {
                        const right = clamp(snapToGrid(originRight + deltaX), originX + 24, currentDesign.canvas_width);
                        element.width = right - originX;
                    }
                    if (resizeDirection.includes("w")) {
                        const left = clamp(snapToGrid(originX + deltaX), 0, originRight - 24);
                        element.x = left;
                        element.width = originRight - left;
                    }
                    if (resizeDirection.includes("s")) {
                        const bottom = clamp(snapToGrid(originBottom + deltaY), originY + 8, currentDesign.canvas_height);
                        element.height = bottom - originY;
                    }
                    if (resizeDirection.includes("n")) {
                        const top = clamp(snapToGrid(originY + deltaY), 0, originBottom - 8);
                        element.y = top;
                        element.height = originBottom - top;
                    }
                } else {
                    element.x = snapToGrid(originX + deltaX);
                    element.y = snapToGrid(originY + deltaY);
                }

                fitElementToCanvas(element);
                node.style.left = `${element.x}px`;
                node.style.top = `${element.y}px`;
                node.style.width = `${element.width}px`;
                node.style.height = `${element.height}px`;
                editor.querySelectorAll("[data-element-property]").forEach((input) => {
                    if (["x", "y", "width", "height"].includes(input.dataset.elementProperty)) {
                        input.value = element[input.dataset.elementProperty];
                    }
                });
                syncElements();
            };
            const end = () => {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", end);
                if (changed) setCustomLayout();
                render();
                if (changed) notifyEditorChange();
            };
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", end, {once: true});
        });

        form.addEventListener("nexora:editor-restore", () => {
            try {
                elements = JSON.parse(elementsInput.value || "[]");
            } catch {
                elements = [];
            }
            layoutMode = normalizeLayoutMode(layoutModeInput?.value || layoutMode);
            selectedId = elements[0]?.id || null;
            render();
        });
        form.addEventListener("submit", syncElements);
        render();
    };

    const initializePublicOverlay = (body) => {
        const canvas = body.querySelector("[data-score-canvas]");
        const stateUrl = body.dataset.stateUrl;
        if (!canvas) return;

        const lastScores = new Map();
        let hasRendered = false;
        const applyState = (state) => {
            const changedParticipantIds = new Set();
            (state.participants || []).forEach((participant) => {
                const participantId = String(participant.id);
                const score = number(participant.score, 0);
                if (hasRendered && lastScores.get(participantId) !== score) {
                    changedParticipantIds.add(participantId);
                }
                lastScores.set(participantId, score);
            });
            applyCanvasDesign(canvas, state);
            window.NexoraBranding?.apply(canvas, state);
            renderElements(
                canvas,
                state.elements || [],
                state.participants || [],
                false,
                null,
                changedParticipantIds,
            );
            hasRendered = true;
        };

        applyState(readInitialState());

        if (stateUrl && window.NexoraPolling) {
            window.NexoraPolling.start({
                url: stateUrl,
                interval: 1500,
                hiddenInterval: 10000,
                onData: applyState,
            });
        }
    };

    document.addEventListener("submit", (event) => {
        const message = event.target.dataset.confirmMessage || event.target.dataset.confirmAction;
        if (message && !window.confirm(message)) event.preventDefault();
    });

    document.querySelectorAll("[data-score-editor]").forEach(initializeEditor);
    const publicBody = document.querySelector("[data-score-overlay-source]");
    if (publicBody) initializePublicOverlay(publicBody);
    requestAnimationFrame(scaleAllPreviews);
    window.addEventListener("resize", scaleAllPreviews);
})();
