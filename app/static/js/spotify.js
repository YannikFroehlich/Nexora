(() => {
    const number = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);
    const resizeDirections = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
    const sourceExtraWidth = 80;
    const sourceExtraHeight = 96;

    const formatTime = (milliseconds) => {
        const totalSeconds = Math.max(Math.floor(number(milliseconds) / 1000), 0);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = String(totalSeconds % 60).padStart(2, "0");
        return `${minutes}:${seconds}`;
    };

    const effectiveProgress = (playback) => {
        if (!playback) {
            return 0;
        }

        const elapsedSinceFetch = playback.is_playing
            ? Math.max(Date.now() - number(playback.fetched_at, Date.now()), 0)
            : 0;
        const duration = Math.max(number(playback.duration_ms), 0);
        const progress = Math.max(number(playback.progress_ms) + elapsedSinceFetch, 0);
        return duration ? Math.min(progress, duration) : progress;
    };

    const createElementContent = (node, element, playback, canvas) => {
        const value = (key, fallback = "") => playback?.[key] || fallback;

        if (element.type === "artwork") {
            const image = document.createElement("img");
            image.alt = "";
            image.dataset.playbackImage = "";
            image.src = value("image_url", canvas.dataset.fallbackImage);
            node.append(image);
            return;
        }

        if (element.type === "progress") {
            const track = document.createElement("span");
            const fill = document.createElement("span");
            track.className = "spotify-progress-track";
            track.setAttribute("aria-hidden", "true");
            fill.dataset.playbackProgress = "";
            track.append(fill);
            node.append(track);
            return;
        }

        if (element.type === "status") {
            const status = document.createElement("span");
            const dot = document.createElement("i");
            const text = document.createElement("span");
            status.className = "spotify-playback-status";
            status.dataset.playbackStatus = "";
            dot.setAttribute("aria-hidden", "true");
            status.append(dot, text);
            node.append(status);
            return;
        }

        const text = document.createElement("span");
        const propertyNames = {
            title: "playbackTitle",
            artist: "playbackArtist",
            album: "playbackAlbum",
            elapsed: "playbackElapsed",
            duration: "playbackDuration",
        };
        text.dataset[propertyNames[element.type] || "playbackValue"] = "";
        node.append(text);
    };

    const updatePlaybackContent = (canvas, playback) => {
        const progress = effectiveProgress(playback);
        const duration = Math.max(number(playback?.duration_ms), 0);
        const progressPercent = duration ? clamp((progress / duration) * 100, 0, 100) : 0;

        canvas.querySelectorAll("[data-playback-title]").forEach((node) => {
            node.textContent = playback?.title || "";
        });
        canvas.querySelectorAll("[data-playback-artist]").forEach((node) => {
            node.textContent = playback?.artist || "";
        });
        canvas.querySelectorAll("[data-playback-album]").forEach((node) => {
            node.textContent = playback?.album || "";
        });
        canvas.querySelectorAll("[data-playback-image]").forEach((node) => {
            node.src = playback?.image_url || canvas.dataset.fallbackImage;
        });
        canvas.querySelectorAll("[data-playback-progress]").forEach((node) => {
            node.style.width = `${progressPercent}%`;
        });
        canvas.querySelectorAll("[data-playback-elapsed]").forEach((node) => {
            node.textContent = formatTime(progress);
        });
        canvas.querySelectorAll("[data-playback-duration]").forEach((node) => {
            node.textContent = formatTime(duration);
        });
        canvas.querySelectorAll("[data-playback-status]").forEach((node) => {
            node.classList.toggle("is-playing", Boolean(playback?.is_playing));
            const label = node.querySelector("span");
            if (label) {
                label.textContent = playback?.is_playing
                    ? canvas.dataset.playingLabel
                    : canvas.dataset.pausedLabel;
            }
        });

        canvas._spotifyPlayback = playback;
    };

    const renderElements = (canvas, elements, playback, editor = false, selectedId = null) => {
        canvas.replaceChildren();

        elements.forEach((element) => {
            const node = document.createElement("div");
            node.className = `spotify-overlay-element spotify-overlay-element--${element.type}`;
            node.dataset.spotifyElement = "";
            node.dataset.elementId = element.id;
            node.dataset.elementType = element.type;
            node.style.left = `${element.x}px`;
            node.style.top = `${element.y}px`;
            node.style.width = `${element.width}px`;
            node.style.height = `${element.height}px`;
            node.style.color = element.color;
            node.style.fontSize = `${element.font_size}px`;
            node.style.borderRadius = `${element.border_radius}px`;
            node.style.setProperty("--spotify-element-color", element.color);
            node.style.setProperty("--spotify-element-background", element.background_color);

            if (editor) {
                node.tabIndex = 0;
                node.setAttribute("role", "button");
                node.setAttribute("aria-label", element.type);
                node.classList.toggle("is-selected", element.id === selectedId);
            }

            createElementContent(node, element, playback, canvas);

            if (editor && element.id === selectedId) {
                resizeDirections.forEach((direction) => {
                    const handle = document.createElement("span");
                    handle.className = `spotify-resize-handle spotify-resize-handle--${direction}`;
                    handle.dataset.resizeHandle = direction;
                    handle.setAttribute("aria-hidden", "true");
                    node.append(handle);
                });
            }

            canvas.append(node);
        });

        updatePlaybackContent(canvas, playback);
    };

    const applyCanvasDesign = (canvas, design) => {
        const red = Number.parseInt(design.background_color.slice(1, 3), 16);
        const green = Number.parseInt(design.background_color.slice(3, 5), 16);
        const blue = Number.parseInt(design.background_color.slice(5, 7), 16);
        const alpha = clamp(number(design.background_opacity, 94), 0, 100) / 100;

        canvas.style.setProperty("--spotify-canvas-width", `${design.canvas_width}px`);
        canvas.style.setProperty("--spotify-canvas-height", `${design.canvas_height}px`);
        canvas.style.setProperty(
            "--spotify-canvas-background",
            `rgba(${red}, ${green}, ${blue}, ${alpha})`,
        );
        canvas.style.setProperty(
            "--spotify-canvas-border-color",
            design.border_color || "#1ed760",
        );
        canvas.style.setProperty(
            "--spotify-canvas-border-width",
            `${clamp(number(design.border_width), 0, 24)}px`,
        );
        canvas.style.setProperty("--spotify-canvas-radius", `${design.corner_radius}px`);
    };

    const scalePreview = (shell) => {
        const canvas = shell.querySelector("[data-spotify-canvas]");
        if (!canvas || shell.closest(".spotify-overlay-source")) {
            return;
        }

        const width = number(getComputedStyle(canvas).getPropertyValue("--spotify-canvas-width"), canvas.offsetWidth);
        const height = number(getComputedStyle(canvas).getPropertyValue("--spotify-canvas-height"), canvas.offsetHeight);
        const padding = shell.classList.contains("spotify-card__preview") ? 22 : 30;
        const availableWidth = Math.max(shell.clientWidth - (padding * 2), 1);
        const maxHeight = shell.classList.contains("spotify-card__preview") ? 190 : 680;
        const scale = Math.min(availableWidth / width, maxHeight / height, 1);
        const renderedWidth = width * scale;
        const renderedHeight = height * scale;

        canvas.style.left = `${Math.max((shell.clientWidth - renderedWidth) / 2, 0)}px`;
        canvas.style.top = `${padding}px`;
        canvas.style.transform = `scale(${scale})`;
        canvas._spotifyScale = scale;
        shell.style.height = `${renderedHeight + (padding * 2)}px`;
    };

    const scaleAllPreviews = () => {
        document.querySelectorAll("[data-spotify-scale-shell]").forEach(scalePreview);
    };

    const initializeEditor = (editor) => {
        const form = editor.querySelector("[data-spotify-form]");
        const elementsInput = editor.querySelector("[data-elements-input]");
        const canvas = editor.querySelector("[data-spotify-canvas]");
        const list = editor.querySelector("[data-element-list]");
        const count = editor.querySelector("[data-element-count]");
        const controls = editor.querySelector("[data-selected-controls]");
        const empty = editor.querySelector("[data-selected-empty]");
        const selectedTitle = editor.querySelector("[data-selected-element-title]");
        const textSetting = editor.querySelector("[data-text-setting]");
        const progressSetting = editor.querySelector("[data-progress-setting]");
        const widthInput = editor.querySelector("#id_canvas_width");
        const heightInput = editor.querySelector("#id_canvas_height");
        const backgroundInput = editor.querySelector("#id_background_color");
        const opacityInput = editor.querySelector("#id_background_opacity");
        const backgroundColorValue = editor.querySelector("[data-background-color-value]");
        const opacityRange = editor.querySelector("[data-background-opacity-range]");
        const opacityValue = editor.querySelector("[data-background-opacity-value]");
        const borderColorInput = editor.querySelector("#id_border_color");
        const borderWidthInput = editor.querySelector("#id_border_width");
        const radiusInput = editor.querySelector("#id_corner_radius");
        const previewWidth = editor.querySelector("[data-preview-width]");
        const previewHeight = editor.querySelector("[data-preview-height]");
        const sourceWidths = editor.querySelectorAll("[data-source-width]");
        const sourceHeights = editor.querySelectorAll("[data-source-height]");
        const gridToggle = editor.querySelector("[data-grid-toggle]");
        const gridSizeInput = editor.querySelector("[data-grid-size]");
        const emptySelectedTitle = selectedTitle.textContent;

        if (!form || !elementsInput || !canvas) {
            return;
        }

        let elements;
        try {
            elements = JSON.parse(elementsInput.value || "[]");
        } catch {
            elements = [];
        }

        const labels = {};
        editor.querySelectorAll("[data-add-element]").forEach((button) => {
            labels[button.dataset.addElement] = button.dataset.elementLabel;
        });

        let selectedId = elements[0]?.id || null;
        let nextId = 0;
        let gridEnabled = false;
        let gridSize = 10;
        const gridStorageKey = "nexora-spotify-editor-grid";

        try {
            const savedGrid = JSON.parse(localStorage.getItem(gridStorageKey) || "null");
            gridEnabled = Boolean(savedGrid?.enabled);
            gridSize = [5, 10, 20, 40].includes(number(savedGrid?.size))
                ? number(savedGrid.size)
                : 10;
        } catch {
            // Grid preferences are optional when browser storage is unavailable.
        }

        const samplePlayback = {
            title: "Midnight Drive",
            artist: "Nova Waves",
            album: "Neon Horizons",
            image_url: "",
            progress_ms: 102000,
            duration_ms: 228000,
            is_playing: true,
            fetched_at: Date.now(),
        };

        const selectedElement = () => elements.find((element) => element.id === selectedId) || null;
        const syncElements = () => {
            elementsInput.value = JSON.stringify(elements);
        };
        const snapToGrid = (value) => gridEnabled
            ? Math.round(value / gridSize) * gridSize
            : Math.round(value);
        const saveGridPreference = () => {
            try {
                localStorage.setItem(
                    gridStorageKey,
                    JSON.stringify({enabled: gridEnabled, size: gridSize}),
                );
            } catch {
                // The editor continues to work without persistent preferences.
            }
        };
        const applyGridState = () => {
            gridToggle.checked = gridEnabled;
            gridSizeInput.value = String(gridSize);
            gridSizeInput.disabled = !gridEnabled;
            canvas.classList.toggle("is-grid-enabled", gridEnabled);
            canvas.style.setProperty("--spotify-grid-size", `${gridSize}px`);
        };

        const design = () => ({
            canvas_width: clamp(number(widthInput.value, 720), 240, 1920),
            canvas_height: clamp(number(heightInput.value, 220), 120, 1080),
            background_color: backgroundInput.value || "#121212",
            background_opacity: clamp(number(opacityInput.value, 94), 0, 100),
            border_color: borderColorInput.value || "#1ed760",
            border_width: clamp(number(borderWidthInput.value), 0, 24),
            corner_radius: clamp(number(radiusInput.value, 26), 0, 80),
        });

        const fitElementToCanvas = (element) => {
            const currentDesign = design();
            element.width = clamp(number(element.width, 120), 24, currentDesign.canvas_width);
            element.height = clamp(number(element.height, 32), 8, currentDesign.canvas_height);
            element.x = clamp(number(element.x), 0, Math.max(currentDesign.canvas_width - element.width, 0));
            element.y = clamp(number(element.y), 0, Math.max(currentDesign.canvas_height - element.height, 0));
        };

        const snapElementPosition = (element) => {
            const currentDesign = design();
            element.x = clamp(
                snapToGrid(element.x),
                0,
                Math.max(currentDesign.canvas_width - element.width, 0),
            );
            element.y = clamp(
                snapToGrid(element.y),
                0,
                Math.max(currentDesign.canvas_height - element.height, 0),
            );
        };

        const updateGeometryControls = (element) => {
            ["x", "y", "width", "height"].forEach((property) => {
                const input = editor.querySelector(`[data-element-property="${property}"]`);
                if (input) input.value = element[property];
            });
        };

        const updateSelectedControls = () => {
            const element = selectedElement();
            controls.hidden = !element;
            empty.hidden = Boolean(element);
            selectedTitle.textContent = element ? (labels[element.type] || element.type) : emptySelectedTitle;

            if (!element) {
                return;
            }

            editor.querySelectorAll("[data-element-property]").forEach((input) => {
                input.value = element[input.dataset.elementProperty];
            });
            textSetting.hidden = ["artwork", "progress"].includes(element.type);
            progressSetting.hidden = element.type !== "progress";
        };

        const renderList = () => {
            list.replaceChildren();
            count.textContent = elements.length;

            elements.forEach((element) => {
                const button = document.createElement("button");
                const label = document.createElement("span");
                const position = document.createElement("span");
                button.type = "button";
                button.className = "element-list__item";
                button.dataset.selectElement = element.id;
                button.classList.toggle("is-selected", element.id === selectedId);
                label.textContent = labels[element.type] || element.type;
                position.textContent = `${element.x} / ${element.y}`;
                button.append(label, position);
                list.append(button);
            });
        };

        const render = () => {
            const currentDesign = design();
            elements.forEach(fitElementToCanvas);
            applyCanvasDesign(canvas, currentDesign);
            applyGridState();
            renderElements(canvas, elements, samplePlayback, true, selectedId);
            renderList();
            updateSelectedControls();
            syncElements();
            if (backgroundColorValue) {
                backgroundColorValue.textContent = currentDesign.background_color.toUpperCase();
            }
            if (opacityRange) {
                opacityRange.value = String(currentDesign.background_opacity);
                opacityRange.style.setProperty(
                    "--spotify-opacity-value",
                    `${currentDesign.background_opacity}%`,
                );
            }
            if (opacityValue) {
                opacityValue.textContent = `${currentDesign.background_opacity}%`;
            }
            previewWidth.textContent = currentDesign.canvas_width;
            previewHeight.textContent = currentDesign.canvas_height;
            sourceWidths.forEach((node) => {
                node.textContent = currentDesign.canvas_width + sourceExtraWidth;
            });
            sourceHeights.forEach((node) => {
                node.textContent = currentDesign.canvas_height + sourceExtraHeight;
            });
            requestAnimationFrame(scaleAllPreviews);
        };

        const select = (elementId, focus = false) => {
            selectedId = elementId;
            render();
            if (focus) {
                canvas.querySelector(`[data-element-id="${CSS.escape(elementId)}"]`)?.focus();
            }
        };

        const removeSelectedElement = (focusNext = false) => {
            if (!selectedId) return;

            elements = elements.filter((element) => element.id !== selectedId);
            selectedId = elements[0]?.id || null;
            render();

            if (focusNext && selectedId) {
                requestAnimationFrame(() => {
                    canvas.querySelector(`[data-element-id="${CSS.escape(selectedId)}"]`)?.focus();
                });
            }
        };

        const defaultsFor = (type) => {
            const currentDesign = design();
            const offset = 18 + ((elements.length * 18) % 100);
            const base = {
                id: `element-${Date.now().toString(36)}-${nextId += 1}`,
                type,
                x: offset,
                y: offset,
                width: 260,
                height: 38,
                font_size: 18,
                color: "#ffffff",
                background_color: "#535353",
                border_radius: 8,
            };

            if (type === "title") Object.assign(base, {width: 380, height: 50, font_size: 28});
            if (type === "artist") Object.assign(base, {width: 340, font_size: 18, color: "#b3b3b3"});
            if (type === "album") Object.assign(base, {width: 340, font_size: 15, color: "#b3b3b3"});
            if (type === "artwork") Object.assign(base, {width: 150, height: 150, color: "#1ed760", border_radius: 16});
            if (type === "progress") Object.assign(base, {width: 360, height: 12, color: "#1ed760", border_radius: 8});
            if (["elapsed", "duration"].includes(type)) Object.assign(base, {width: 70, height: 24, font_size: 13, color: "#b3b3b3"});
            if (type === "status") Object.assign(base, {width: 150, height: 30, font_size: 14, color: "#1ed760"});

            base.width = Math.min(base.width, currentDesign.canvas_width);
            base.height = Math.min(base.height, currentDesign.canvas_height);
            fitElementToCanvas(base);
            snapElementPosition(base);
            return base;
        };

        editor.addEventListener("click", (event) => {
            const addButton = event.target.closest("[data-add-element]");
            if (addButton) {
                const element = defaultsFor(addButton.dataset.addElement);
                elements.push(element);
                selectedId = element.id;
                render();
                return;
            }

            const listButton = event.target.closest("[data-select-element]");
            if (listButton) {
                select(listButton.dataset.selectElement, true);
                return;
            }

            if (event.target.closest("[data-delete-element]")) {
                removeSelectedElement();
            }
        });

        editor.querySelectorAll("[data-element-property]").forEach((input) => {
            input.addEventListener("input", () => {
                const element = selectedElement();
                if (!element) return;
                const property = input.dataset.elementProperty;
                element[property] = input.type === "color" ? input.value : number(input.value, element[property]);
                fitElementToCanvas(element);
                renderElements(canvas, elements, samplePlayback, true, selectedId);
                renderList();
                syncElements();
            });
        });

        [
            widthInput,
            heightInput,
            backgroundInput,
            opacityInput,
            borderColorInput,
            borderWidthInput,
            radiusInput,
        ].forEach((input) => {
            input.addEventListener("input", render);
        });

        opacityRange?.addEventListener("input", () => {
            opacityInput.value = opacityRange.value;
            render();
        });

        gridToggle.addEventListener("change", () => {
            gridEnabled = gridToggle.checked;
            applyGridState();
            saveGridPreference();
        });

        gridSizeInput.addEventListener("change", () => {
            gridSize = [5, 10, 20, 40].includes(number(gridSizeInput.value))
                ? number(gridSizeInput.value)
                : 10;
            applyGridState();
            saveGridPreference();
        });

        canvas.addEventListener("click", (event) => {
            const node = event.target.closest("[data-spotify-element]");
            if (node) select(node.dataset.elementId, true);
        });

        canvas.addEventListener("keydown", (event) => {
            const node = event.target.closest("[data-spotify-element]");
            if (!node) return;

            if (event.key === "Delete") {
                event.preventDefault();
                selectedId = node.dataset.elementId;
                removeSelectedElement(true);
                return;
            }

            if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault();
            selectedId = node.dataset.elementId;
            const element = selectedElement();
            const step = gridEnabled
                ? gridSize * (event.shiftKey ? 5 : 1)
                : (event.shiftKey ? 10 : 1);

            if (gridEnabled) snapElementPosition(element);
            if (event.key === "ArrowLeft") element.x -= step;
            if (event.key === "ArrowRight") element.x += step;
            if (event.key === "ArrowUp") element.y -= step;
            if (event.key === "ArrowDown") element.y += step;
            fitElementToCanvas(element);
            render();
            canvas.querySelector(`[data-element-id="${CSS.escape(element.id)}"]`)?.focus();
        });

        canvas.addEventListener("pointerdown", (event) => {
            const node = event.target.closest("[data-spotify-element]");
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
            const scale = canvas._spotifyScale || 1;

            node.focus({preventScroll: true});

            canvas.querySelectorAll("[data-spotify-element]").forEach((item) => {
                item.classList.toggle("is-selected", item === node);
            });
            renderList();
            updateSelectedControls();

            const move = (moveEvent) => {
                const deltaX = Math.round((moveEvent.clientX - startX) / scale);
                const deltaY = Math.round((moveEvent.clientY - startY) / scale);

                if (resizeDirection) {
                    if (resizeDirection.includes("e")) {
                        const right = clamp(
                            snapToGrid(originRight + deltaX),
                            originX + 24,
                            currentDesign.canvas_width,
                        );
                        element.width = right - originX;
                    }
                    if (resizeDirection.includes("w")) {
                        const left = clamp(
                            snapToGrid(originX + deltaX),
                            0,
                            originRight - 24,
                        );
                        element.x = left;
                        element.width = originRight - left;
                    }
                    if (resizeDirection.includes("s")) {
                        const bottom = clamp(
                            snapToGrid(originBottom + deltaY),
                            originY + 8,
                            currentDesign.canvas_height,
                        );
                        element.height = bottom - originY;
                    }
                    if (resizeDirection.includes("n")) {
                        const top = clamp(
                            snapToGrid(originY + deltaY),
                            0,
                            originBottom - 8,
                        );
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
                updateGeometryControls(element);
                syncElements();
            };
            const end = () => {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", end);
                renderList();
            };

            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", end, {once: true});
        });

        form.addEventListener("submit", syncElements);
        render();
    };

    const initializePublicOverlay = (body) => {
        const canvas = body.querySelector("[data-spotify-canvas]");
        const stateUrl = body.dataset.stateUrl;
        if (!canvas || !stateUrl) return;

        const update = async () => {
            try {
                const response = await fetch(stateUrl, {cache: "no-store", credentials: "same-origin"});
                if (!response.ok) return;
                const state = await response.json();
                applyCanvasDesign(canvas, state);
                renderElements(canvas, state.elements || [], state.playback || {}, false);
            } catch {
                // Keep the last rendered state while Spotify or the network is unavailable.
            }
        };

        update();
        window.setInterval(update, 5000);
        window.setInterval(() => {
            if (canvas._spotifyPlayback) updatePlaybackContent(canvas, canvas._spotifyPlayback);
        }, 250);
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

    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");
        if (!copyButton) return;

        try {
            await copyText(copyButton.dataset.copyUrl);
            const toast = document.querySelector("[data-copy-toast]");
            if (toast) {
                toast.hidden = false;
                window.setTimeout(() => { toast.hidden = true; }, 2200);
            }
        } catch {
            // The readonly input remains available for manual copying.
        }
    });

    document.addEventListener("submit", (event) => {
        const message = event.target.dataset.confirmMessage;
        if (message && !window.confirm(message)) event.preventDefault();
    });

    document.querySelectorAll("[data-spotify-editor]").forEach(initializeEditor);
    const publicBody = document.querySelector("[data-spotify-overlay-source]");
    if (publicBody) initializePublicOverlay(publicBody);

    requestAnimationFrame(scaleAllPreviews);
    window.addEventListener("resize", scaleAllPreviews);
})();
