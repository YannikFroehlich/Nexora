(() => {
    const number = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);
    const resizeDirections = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
    const sourceExtraWidth = 80;
    const sourceExtraHeight = 96;

    const defaultState = () => ({
        name: "Score HUD",
        canvas_width: 960,
        canvas_height: 240,
        background_color: "#0f172a",
        background_opacity: 72,
        border_color: "#38bdf8",
        border_width: 1,
        corner_radius: 28,
        elements: [],
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

    const hexToRgba = (hex, opacity) => {
        const normalized = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : "#0f172a";
        const red = Number.parseInt(normalized.slice(1, 3), 16);
        const green = Number.parseInt(normalized.slice(3, 5), 16);
        const blue = Number.parseInt(normalized.slice(5, 7), 16);
        return `rgba(${red}, ${green}, ${blue}, ${clamp(number(opacity, 72), 0, 100) / 100})`;
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

    const createElementContent = (node, element, participant) => {
        if (element.type === "participant_image") {
            if (participant?.image_url) {
                const image = document.createElement("img");
                image.alt = "";
                image.src = participant.image_url;
                node.append(image);
            } else {
                const initials = document.createElement("span");
                initials.textContent = participant?.initials || "?";
                node.append(initials);
            }
            return;
        }

        const text = document.createElement("span");
        text.textContent = element.type === "participant_score"
            ? String(participant?.score ?? 0)
            : (participant?.name || "");
        node.append(text);
    };

    const renderElements = (canvas, elements, participants, editor = false, selectedId = null) => {
        const participantsById = participantMap(participants);
        canvas.replaceChildren();

        elements.forEach((element) => {
            const participant = participantsById.get(String(element.participant_id));
            if (!participant) return;

            const node = document.createElement("div");
            node.className = `score-overlay-element score-overlay-element--${element.type}`;
            node.dataset.scoreElement = "";
            node.dataset.elementId = element.id;
            node.dataset.elementType = element.type;
            node.style.left = `${element.x}px`;
            node.style.top = `${element.y}px`;
            node.style.width = `${element.width}px`;
            node.style.height = `${element.height}px`;
            node.style.color = element.color;
            node.style.backgroundColor = element.background_color;
            node.style.fontSize = `${element.font_size}px`;
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

            canvas.append(node);
        });
    };

    const applyCanvasDesign = (canvas, design) => {
        canvas.style.setProperty("--score-canvas-width", `${number(design.canvas_width, 960)}px`);
        canvas.style.setProperty("--score-canvas-height", `${number(design.canvas_height, 240)}px`);
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
        const scale = Math.min(availableWidth / width, 620 / height, 1);
        const renderedWidth = width * scale;
        const renderedHeight = height * scale;

        canvas.style.left = `${Math.max((shell.clientWidth - renderedWidth) / 2, 0)}px`;
        canvas.style.top = `${padding}px`;
        canvas.style.transform = `scale(${scale})`;
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
        let gridEnabled = false;
        let gridSize = 10;

        const design = () => ({
            canvas_width: clamp(number(widthInput.value, 960), 320, 1920),
            canvas_height: clamp(number(heightInput.value, 240), 140, 1080),
            background_color: backgroundInput.value || "#0f172a",
            background_opacity: clamp(number(opacityInput.value, 72), 0, 100),
            border_color: borderColorInput.value || "#38bdf8",
            border_width: clamp(number(borderWidthInput.value), 0, 24),
            corner_radius: clamp(number(radiusInput.value, 28), 0, 80),
        });

        const selectedElement = () => elements.find((element) => element.id === selectedId) || null;
        const notifyEditorChange = () => form.dispatchEvent(new CustomEvent("nexora:editor-change", {bubbles: true}));
        const syncElements = () => {
            elementsInput.value = JSON.stringify(elements);
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
            const currentDesign = design();
            elements = [];
            participants.forEach((participant, index) => {
                if (mode === "duel" && participants.length === 2) {
                    const left = index === 0;
                    const imageX = left ? 34 : currentDesign.canvas_width - 154;
                    const nameX = left ? 142 : currentDesign.canvas_width - 402;
                    const scoreX = left ? 302 : currentDesign.canvas_width - 502;
                    elements.push(
                        {
                            id: `participant-${participant.id}-image`,
                            type: "participant_image",
                            participant_id: String(participant.id),
                            x: imageX,
                            y: 50,
                            width: 120,
                            height: 120,
                            font_size: 38,
                            color: "#ffffff",
                            background_color: participant.accent_color,
                            border_radius: 24,
                            text_align: "center",
                        },
                        {
                            id: `participant-${participant.id}-name`,
                            type: "participant_name",
                            participant_id: String(participant.id),
                            x: nameX,
                            y: 62,
                            width: 240,
                            height: 40,
                            font_size: 28,
                            color: "#ffffff",
                            background_color: "#111827",
                            border_radius: 10,
                            text_align: left ? "left" : "right",
                        },
                        {
                            id: `participant-${participant.id}-score`,
                            type: "participant_score",
                            participant_id: String(participant.id),
                            x: scoreX,
                            y: 103,
                            width: 140,
                            height: 78,
                            font_size: 62,
                            color: "#ffffff",
                            background_color: participant.accent_color,
                            border_radius: 18,
                            text_align: "center",
                        },
                    );
                    return;
                }

                const rowHeight = Math.max(Math.floor((currentDesign.canvas_height - 34) / participants.length), 54);
                const y = 18 + (index * rowHeight);
                elements.push(
                    {
                        id: `participant-${participant.id}-image`,
                        type: "participant_image",
                        participant_id: String(participant.id),
                        x: 24,
                        y,
                        width: Math.min(rowHeight - 8, 70),
                        height: Math.min(rowHeight - 8, 70),
                        font_size: 22,
                        color: "#ffffff",
                        background_color: participant.accent_color,
                        border_radius: 14,
                        text_align: "center",
                    },
                    {
                        id: `participant-${participant.id}-name`,
                        type: "participant_name",
                        participant_id: String(participant.id),
                        x: 100,
                        y: y + 8,
                        width: Math.max(currentDesign.canvas_width - 280, 180),
                        height: Math.min(rowHeight - 16, 42),
                        font_size: 24,
                        color: "#ffffff",
                        background_color: "#111827",
                        border_radius: 9,
                        text_align: "left",
                    },
                    {
                        id: `participant-${participant.id}-score`,
                        type: "participant_score",
                        participant_id: String(participant.id),
                        x: Math.max(currentDesign.canvas_width - 150, 170),
                        y,
                        width: 120,
                        height: Math.min(rowHeight - 8, 70),
                        font_size: 42,
                        color: "#ffffff",
                        background_color: participant.accent_color,
                        border_radius: 14,
                        text_align: "center",
                    },
                );
            });
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
                    ["-1", "minus", participantList.dataset.minusLabel],
                    ["+1", "plus", participantList.dataset.plusLabel],
                    ["reset", "reset", participantList.dataset.resetLabel],
                    ["save", "save", participantList.dataset.saveLabel],
                    ["delete", "delete", participantList.dataset.deleteLabel],
                ].forEach(([action, className, label]) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = `score-icon-button score-icon-button--${className}`;
                    button.dataset.participantAction = action;
                    button.textContent = action === "+1" ? "+" : action === "-1" ? "-" : action[0].toUpperCase();
                    button.setAttribute("aria-label", label || action);
                    button.title = label || action;
                    actions.append(button);
                });

                row.append(badge, formWrap, score, actions);
                participantList.append(row);
            });
        };

        const render = () => {
            ensureParticipantElements();
            const currentDesign = design();
            elements.forEach(fitElementToCanvas);
            applyCanvasDesign(canvas, currentDesign);
            window.NexoraBranding?.apply(canvas, currentDesign);
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
                    participants = nextState.participants || participants;
                    elements = nextState.elements || elements;
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
                        participants = nextState.participants || participants;
                        elements = nextState.elements || elements;
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
                    participants = nextState.participants || participants;
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
                const property = input.dataset.elementProperty;
                element[property] = input.type === "color" || input.tagName === "SELECT"
                    ? input.value
                    : number(input.value, element[property]);
                fitElementToCanvas(element);
                renderElements(canvas, elements, participants, true, selectedId);
                renderList();
                syncElements();
            });
            input.addEventListener("change", notifyEditorChange);
        });

        [widthInput, heightInput, backgroundInput, opacityInput, borderColorInput, borderWidthInput, radiusInput]
            .forEach((input) => {
                input?.addEventListener("input", () => {
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

        const applyState = (state) => {
            applyCanvasDesign(canvas, state);
            window.NexoraBranding?.apply(canvas, state);
            renderElements(canvas, state.elements || [], state.participants || [], false);
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
