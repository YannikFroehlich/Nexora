(() => {
    const designPresets = {
        minimal: {
            background_color: "#111827",
            background_opacity: 72,
            text_color: "#f8fafc",
            accent_color: "#14b8a6",
            border_color: "#334155",
            border_width: 0,
            corner_radius: 12,
            padding: 22,
            overlay_width: 420,
            overlay_height: 0,
            text_size: 15,
            label_text_size: 10,
            title_text_size: 20,
            total_text_size: 14,
            game_text_size: 15,
            game_score_text_size: 12,
            pager_text_size: 12,
            page_interval_seconds: 4,
            item_spacing: 8,
            shadow_enabled: false,
            show_games_list: true,
        },
        glass: {
            background_color: "#111827",
            background_opacity: 82,
            text_color: "#f8fafc",
            accent_color: "#14b8a6",
            border_color: "#2dd4bf",
            border_width: 1,
            corner_radius: 22,
            padding: 24,
            overlay_width: 460,
            overlay_height: 0,
            text_size: 16,
            label_text_size: 10,
            title_text_size: 20,
            total_text_size: 14,
            game_text_size: 15,
            game_score_text_size: 12,
            pager_text_size: 12,
            page_interval_seconds: 4,
            item_spacing: 9,
            shadow_enabled: true,
            show_games_list: true,
        },
        neon: {
            background_color: "#09090b",
            background_opacity: 88,
            text_color: "#f8fafc",
            accent_color: "#facc15",
            border_color: "#22d3ee",
            border_width: 2,
            corner_radius: 18,
            padding: 24,
            overlay_width: 500,
            overlay_height: 0,
            text_size: 17,
            label_text_size: 11,
            title_text_size: 22,
            total_text_size: 15,
            game_text_size: 16,
            game_score_text_size: 13,
            pager_text_size: 12,
            page_interval_seconds: 4,
            item_spacing: 10,
            shadow_enabled: true,
            show_games_list: true,
        },
    };

    const fieldIds = {
        title: "id_title",
        design_template: "id_design_template",
        background_color: "id_background_color",
        background_opacity: "id_background_opacity",
        text_color: "id_text_color",
        accent_color: "id_accent_color",
        border_color: "id_border_color",
        border_width: "id_border_width",
        corner_radius: "id_corner_radius",
        padding: "id_padding",
        overlay_width: "id_overlay_width",
        overlay_height: "id_overlay_height",
        text_size: "id_text_size",
        label_text_size: "id_label_text_size",
        title_text_size: "id_title_text_size",
        total_text_size: "id_total_text_size",
        game_text_size: "id_game_text_size",
        game_score_text_size: "id_game_score_text_size",
        pager_text_size: "id_pager_text_size",
        page_interval_seconds: "id_page_interval_seconds",
        item_spacing: "id_item_spacing",
        shadow_enabled: "id_shadow_enabled",
        show_games_list: "id_show_games_list",
    };

    const iconPaths = {
        decrease: ["M5 12h14"],
        increase: ["M12 5v14", "M5 12h14"],
        edit: [
            "M12 20h9",
            "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z",
        ],
        delete: [
            "M3 6h18",
            "M8 6V4h8v2",
            "M19 6l-1 14H6L5 6",
            "M10 11v6",
            "M14 11v6",
        ],
    };

    const getField = (name) => document.getElementById(fieldIds[name]);

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

    const numberValue = (name, fallback, min, max) => {
        const field = getField(name);
        const value = Number.parseInt(field?.value, 10);

        if (Number.isNaN(value)) {
            return fallback;
        }

        return clamp(value, min, max);
    };

    const checkboxValue = (name, fallback) => {
        const field = getField(name);
        return field ? field.checked : fallback;
    };

    const textValue = (name, fallback) => {
        const field = getField(name);
        const value = field?.value?.trim();

        return value || fallback;
    };

    const hexToRgba = (hex, opacity) => {
        const normalized = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : "#111827";
        const red = Number.parseInt(normalized.slice(1, 3), 16);
        const green = Number.parseInt(normalized.slice(3, 5), 16);
        const blue = Number.parseInt(normalized.slice(5, 7), 16);
        const alpha = clamp(Number(opacity), 0, 100) / 100;

        return `rgba(${red}, ${green}, ${blue}, ${alpha.toFixed(2)})`;
    };

    const designFromInputs = () => ({
        template: textValue("design_template", "glass"),
        background_color: textValue("background_color", "#111827"),
        background_opacity: numberValue("background_opacity", 82, 0, 100),
        text_color: textValue("text_color", "#f8fafc"),
        accent_color: textValue("accent_color", "#14b8a6"),
        border_color: textValue("border_color", "#2dd4bf"),
        border_width: numberValue("border_width", 1, 0, 12),
        corner_radius: numberValue("corner_radius", 22, 0, 64),
        padding: numberValue("padding", 24, 8, 64),
        overlay_width: numberValue("overlay_width", 460, 260, 1200),
        overlay_height: numberValue("overlay_height", 0, 0, 1000),
        text_size: numberValue("text_size", 16, 10, 36),
        label_text_size: numberValue("label_text_size", 10, 6, 32),
        title_text_size: numberValue("title_text_size", 20, 10, 64),
        total_text_size: numberValue("total_text_size", 14, 8, 40),
        game_text_size: numberValue("game_text_size", 15, 8, 48),
        game_score_text_size: numberValue("game_score_text_size", 12, 8, 36),
        pager_text_size: numberValue("pager_text_size", 12, 8, 32),
        page_interval_seconds: numberValue("page_interval_seconds", 4, 1, 60),
        item_spacing: numberValue("item_spacing", 9, 4, 28),
        shadow_enabled: checkboxValue("shadow_enabled", true),
        show_games_list: checkboxValue("show_games_list", true),
    });

    const applyDesignToOverlay = (overlay, design) => {
        const background = design.background_rgba || hexToRgba(
            design.background_color,
            design.background_opacity
        );

        overlay.style.setProperty("--wc-bg", background);
        overlay.style.setProperty("--wc-text", design.text_color);
        overlay.style.setProperty("--wc-accent", design.accent_color);
        overlay.style.setProperty("--wc-border", design.border_color);
        overlay.style.setProperty("--wc-border-width", `${design.border_width}px`);
        overlay.style.setProperty("--wc-radius", `${design.corner_radius}px`);
        overlay.style.setProperty("--wc-padding", `${design.padding}px`);
        overlay.style.setProperty("--wc-width", `${design.overlay_width || 460}px`);
        overlay.style.setProperty(
            "--wc-height",
            design.overlay_height > 0 ? `${design.overlay_height}px` : "auto"
        );
        overlay.style.setProperty("--wc-font-size", `${design.text_size || 16}px`);
        overlay.style.setProperty("--wc-label-font-size", `${design.label_text_size || 10}px`);
        overlay.style.setProperty("--wc-title-font-size", `${design.title_text_size || 20}px`);
        overlay.style.setProperty("--wc-total-font-size", `${design.total_text_size || 14}px`);
        overlay.style.setProperty("--wc-game-font-size", `${design.game_text_size || 15}px`);
        overlay.style.setProperty("--wc-game-score-font-size", `${design.game_score_text_size || 12}px`);
        overlay.style.setProperty("--wc-pager-font-size", `${design.pager_text_size || 12}px`);
        overlay.style.setProperty("--wc-item-spacing", `${design.item_spacing || 9}px`);
        overlay.dataset.pageIntervalSeconds = String(design.page_interval_seconds || 4);
        overlay.style.setProperty(
            "--wc-shadow",
            design.shadow_enabled ? "0 18px 48px rgba(0, 0, 0, 0.35)" : "none"
        );

        const gamesList = overlay.querySelector("[data-games-list]");

        if (gamesList) {
            gamesList.hidden = !design.show_games_list;
        }
    };

    const setText = (root, selector, value) => {
        root.querySelectorAll(selector).forEach((node) => {
            node.textContent = value;
        });
    };

    const chunkItems = (items, size) => {
        const chunks = [];

        for (let index = 0; index < items.length; index += size) {
            chunks.push(items.slice(index, index + size));
        }

        return chunks;
    };

    const setupOverlayPager = (overlay) => {
        const pages = Array.from(overlay.querySelectorAll(".winchallenge-overlay__page"));
        const indicator = overlay.querySelector("[data-page-indicator]");
        const currentPage = overlay.querySelector("[data-current-page]");
        const totalPages = overlay.querySelector("[data-total-pages]");

        if (overlay._winchallengePager) {
            window.clearInterval(overlay._winchallengePager);
            overlay._winchallengePager = null;
        }

        if (!pages.length) {
            if (indicator) {
                indicator.hidden = true;
            }
            return;
        }

        let activeIndex = 0;

        const showPage = (index) => {
            activeIndex = index;

            pages.forEach((page, pageIndex) => {
                const isActive = pageIndex === activeIndex;
                page.hidden = !isActive;
                page.classList.toggle("is-active", isActive);
            });

            if (currentPage) {
                currentPage.textContent = String(activeIndex + 1);
            }
        };

        if (indicator) {
            indicator.hidden = pages.length <= 1;
        }

        if (totalPages) {
            totalPages.textContent = String(pages.length);
        }

        showPage(0);

        if (pages.length > 1) {
            const intervalSeconds = Number.parseFloat(overlay.dataset.pageIntervalSeconds || "4");
            const intervalMs = (Number.isNaN(intervalSeconds) ? 4 : clamp(intervalSeconds, 1, 60)) * 1000;

            overlay._winchallengePager = window.setInterval(() => {
                showPage((activeIndex + 1) % pages.length);
            }, intervalMs);
        }
    };

    const renderOverlayGames = (overlay, games) => {
        const list = overlay.querySelector("[data-games-list]");

        if (!list) {
            return;
        }

        list.replaceChildren();

        if (!games.length) {
            const item = document.createElement("p");
            item.className = "winchallenge-overlay__empty";
            item.textContent = list.dataset.emptyLabel || "No games yet";
            list.append(item);
            setupOverlayPager(overlay);
            return;
        }

        const gamesPerPage = Number.parseInt(list.dataset.gamesPerPage || "3", 10);
        const pages = chunkItems(games, gamesPerPage > 0 ? gamesPerPage : 3);

        pages.forEach((gamesPage, pageIndex) => {
            const page = document.createElement("div");
            page.className = "winchallenge-overlay__page";
            page.dataset.pageIndex = pageIndex;
            page.hidden = pageIndex !== 0;
            page.classList.toggle("is-active", pageIndex === 0);

            gamesPage.forEach((game) => {
                const item = document.createElement("article");
                item.className = "winchallenge-overlay__game";
                item.dataset.gameId = game.id;

                const top = document.createElement("div");
                top.className = "winchallenge-overlay__game-top";

                const name = document.createElement("strong");
                name.dataset.gameName = "";
                name.textContent = game.name;

                const badge = document.createElement("span");
                badge.className = "winchallenge-overlay__game-badge";
                badge.innerHTML = `<span data-game-wins>${game.wins}</span>/<span data-game-target-wins>${game.target_wins}</span>`;

                top.append(name, badge);

                const progress = document.createElement("div");
                progress.className = "winchallenge-overlay__game-progress";
                const progressBar = document.createElement("span");
                progressBar.dataset.gameProgress = "";
                progressBar.style.width = `${game.progress_percent}%`;
                progress.append(progressBar);

                item.append(top, progress);
                page.append(item);
            });

            list.append(page);
        });

        setupOverlayPager(overlay);
    };

    const sampleGamesForPreview = (preview) => {
        if (!preview?.dataset.sampleGames) {
            return [];
        }

        try {
            const games = JSON.parse(preview.dataset.sampleGames);

            if (!Array.isArray(games)) {
                return [];
            }

            return games.map((game, index) => {
                const wins = Number.parseInt(game.wins, 10);
                const targetWins = Number.parseInt(game.target_wins, 10);
                const safeWins = Number.isNaN(wins) ? 0 : wins;
                const safeTarget = Number.isNaN(targetWins) || targetWins < 1 ? 1 : targetWins;
                const fallbackProgress = Math.min(Math.round((safeWins / safeTarget) * 100), 100);
                const progress = Number.parseInt(game.progress_percent, 10);

                return {
                    id: game.id || `sample-${index + 1}`,
                    name: game.name || "Game",
                    wins: safeWins,
                    target_wins: safeTarget,
                    progress_percent: Number.isNaN(progress) ? fallbackProgress : clamp(progress, 0, 100),
                };
            });
        } catch {
            return [];
        }
    };

    const syncPresetButtons = () => {
        const selectedPreset = textValue("design_template", "glass");

        document.querySelectorAll("[data-preset-button]").forEach((button) => {
            const isActive = button.dataset.preset === selectedPreset;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", String(isActive));
        });
    };

    const applyState = (state) => {
        document.querySelectorAll("[data-winchallenge-overlay]").forEach((overlay) => {
            applyDesignToOverlay(overlay, state.design);
            setText(overlay, "[data-overlay-title]", state.title);
            setText(overlay, "[data-total-wins]", state.total_wins);

            renderOverlayGames(overlay, state.games);
        });

        setText(document, "[data-total-wins]", state.total_wins);
        setText(document, "[data-games-count]", state.games.length);
        renderManageGames(state);
    };

    const updatePreviewFromInputs = () => {
        const editor = document.querySelector("[data-winchallenge-editor]");

        if (!editor) {
            return;
        }

        const design = designFromInputs();
        const title = textValue("title", "Winchallenge");

        document.querySelectorAll("[data-winchallenge-preview] [data-winchallenge-overlay]").forEach((overlay) => {
            applyDesignToOverlay(overlay, design);
            setText(overlay, "[data-overlay-title]", title);

            const preview = overlay.closest("[data-winchallenge-preview]");
            const sampleGames = sampleGamesForPreview(preview);

            if (sampleGames.length) {
                renderOverlayGames(overlay, sampleGames);
                setText(
                    overlay,
                    "[data-total-wins]",
                    String(sampleGames.reduce((total, game) => total + game.wins, 0))
                );
            } else {
                setupOverlayPager(overlay);
            }
        });

        syncPresetButtons();
    };

    const applyPreset = (presetName) => {
        const preset = designPresets[presetName];

        if (!preset) {
            return;
        }

        Object.entries(preset).forEach(([name, value]) => {
            const field = getField(name);

            if (!field) {
                return;
            }

            if (field.type === "checkbox") {
                field.checked = Boolean(value);
            } else {
                field.value = value;
            }
        });

        updatePreviewFromInputs();
    };

    const getCsrfToken = () => {
        const tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");

        if (tokenInput) {
            return tokenInput.value;
        }

        return document.cookie
            .split("; ")
            .find((row) => row.startsWith("csrftoken="))
            ?.split("=")[1] || "";
    };

    const postForm = async (url, data) => {
        const body = new URLSearchParams();

        Object.entries(data).forEach(([key, value]) => {
            body.append(key, value);
        });

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
            throw new Error(payload.error || formatFormErrors(payload.errors) || "Request failed");
        }

        return payload;
    };

    const formatFormErrors = (errors) => {
        if (!errors || typeof errors !== "object") {
            return "";
        }

        return Object.entries(errors)
            .flatMap(([fieldName, fieldErrors]) => (
                Array.isArray(fieldErrors)
                    ? fieldErrors.map((fieldError) => `${fieldName}: ${fieldError.message || fieldError}`)
                    : [`${fieldName}: ${fieldErrors}`]
            ))
            .join("\n");
    };

    const urlFromTemplate = (template, id) => template.replace("/0/", `/${id}/`);

    const renderManageGames = (state) => {
        const list = document.querySelector("[data-game-list]");

        if (!list) {
            return;
        }

        list.replaceChildren();

        if (!state.games.length) {
            const empty = document.createElement("p");
            empty.className = "empty-inline";
            empty.dataset.emptyGames = "";
            empty.textContent = list.dataset.emptyLabel || "No games added yet.";
            list.append(empty);
            return;
        }

        state.games.forEach((game) => {
            const row = document.createElement("article");
            row.className = "game-row";
            row.dataset.gameRow = game.id;

            const info = document.createElement("div");
            info.className = "game-row__body";

            const name = document.createElement("strong");
            name.className = "game-row__title";
            name.dataset.gameName = "";
            name.textContent = game.name;

            const wins = document.createElement("span");
            wins.className = "game-row__score";
            const winsValue = document.createElement("span");
            winsValue.dataset.gameWins = "";
            winsValue.textContent = game.wins;
            const divider = document.createElement("span");
            divider.setAttribute("aria-hidden", "true");
            divider.textContent = "/";
            const targetValue = document.createElement("span");
            targetValue.dataset.gameTargetWins = "";
            targetValue.textContent = game.target_wins;
            const winsLabel = document.createElement("span");
            winsLabel.textContent = list.dataset.winsLabel || "Wins";
            wins.append(
                winsValue,
                divider,
                targetValue,
                winsLabel
            );
            info.append(name, wins);

            const actions = document.createElement("div");
            actions.className = "game-row__actions";

            const decrease = createGameButton("decrease", "js-win-change", list.dataset.decreaseLabel);
            decrease.dataset.delta = "-1";
            decrease.dataset.url = urlFromTemplate(list.dataset.winsUrlTemplate, game.id);

            const increase = createGameButton("increase", "js-win-change", list.dataset.increaseLabel);
            increase.dataset.delta = "1";
            increase.dataset.url = urlFromTemplate(list.dataset.winsUrlTemplate, game.id);

            const rename = createGameButton("edit", "js-game-rename", list.dataset.editLabel);
            rename.dataset.url = urlFromTemplate(list.dataset.renameUrlTemplate, game.id);

            const remove = createGameButton("delete", "js-game-delete danger-icon", list.dataset.deleteLabel);
            remove.dataset.url = urlFromTemplate(list.dataset.deleteUrlTemplate, game.id);

            actions.append(decrease, increase, rename, remove);
            row.append(info, actions);
            list.append(row);
        });
    };

    const createGameButton = (iconName, className, label) => {
        const button = document.createElement("button");
        button.className = `icon-button ${className}`;
        button.type = "button";
        button.append(createIcon(iconName));
        button.setAttribute("aria-label", label || iconName);
        button.title = label || iconName;

        return button;
    };

    const createIcon = (iconName) => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.classList.add("icon-button__icon");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("stroke-width", "2");

        (iconPaths[iconName] || []).forEach((pathData) => {
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", pathData);
            svg.append(path);
        });

        return svg;
    };

    const showToast = () => {
        const toast = document.querySelector("[data-copy-toast]");

        if (!toast) {
            return;
        }

        toast.hidden = false;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.hidden = true;
        }, 2200);
    };

    const copyToClipboard = async (value) => {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(value);
            return;
        }

        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    };

    const handleAjaxError = (error) => {
        window.alert(error.message);
    };

    const initEditor = () => {
        const editor = document.querySelector("[data-winchallenge-editor]");

        if (!editor) {
            return;
        }

        editor.querySelectorAll("[data-preset-button]").forEach((button) => {
            button.addEventListener("click", () => {
                const field = getField("design_template");

                if (!field || !button.dataset.preset) {
                    return;
                }

                field.value = button.dataset.preset;
                field.dispatchEvent(new Event("change", { bubbles: true }));
            });
        });

        editor.querySelectorAll("input, select").forEach((control) => {
            control.addEventListener("input", updatePreviewFromInputs);
            control.addEventListener("change", updatePreviewFromInputs);
        });

        getField("design_template")?.addEventListener("change", (event) => {
            applyPreset(event.target.value);
        });

        updatePreviewFromInputs();
    };

    const initOverlayPolling = () => {
        const source = document.querySelector("[data-overlay-source]");

        if (!source) {
            return;
        }

        let lastUpdated = source.dataset.lastUpdated || "";
        const stateUrl = source.dataset.stateUrl;

        const poll = async () => {
            try {
                const response = await fetch(stateUrl, {
                    cache: "no-store",
                    headers: {
                        Accept: "application/json",
                    },
                });

                if (!response.ok) {
                    return;
                }

                const state = await response.json();

                if (state.updated_at !== lastUpdated) {
                    lastUpdated = state.updated_at;
                    source.dataset.lastUpdated = lastUpdated;
                    applyState(state);
                }
            } catch {
                // OBS should keep the last rendered state during short network hiccups.
            }
        };

        window.setInterval(poll, 1500);
        poll();
    };

    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");
        const winButton = event.target.closest(".js-win-change");
        const renameButton = event.target.closest(".js-game-rename");
        const deleteButton = event.target.closest(".js-game-delete");

        if (copyButton) {
            await copyToClipboard(copyButton.dataset.copyUrl);
            showToast();
            return;
        }

        if (winButton) {
            winButton.disabled = true;

            try {
                applyState(await postForm(winButton.dataset.url, { delta: winButton.dataset.delta }));
            } catch (error) {
                handleAjaxError(error);
            } finally {
                winButton.disabled = false;
            }

            return;
        }

        if (renameButton) {
            const list = document.querySelector("[data-game-list]");
            const currentName = renameButton.closest("[data-game-row]")?.querySelector("[data-game-name]")?.textContent || "";
            const nextName = window.prompt(list?.dataset.renamePrompt || "Rename game", currentName);

            if (!nextName) {
                return;
            }

            const currentTarget = renameButton.closest("[data-game-row]")?.querySelector("[data-game-target-wins]")?.textContent || "10";
            const currentWins = renameButton.closest("[data-game-row]")?.querySelector("[data-game-wins]")?.textContent || "0";
            const nextWins = window.prompt(list?.dataset.winsPrompt || "Wins", currentWins);

            if (nextWins === null) {
                return;
            }

            const nextTarget = window.prompt(list?.dataset.targetPrompt || "Target wins", currentTarget);

            if (nextTarget === null) {
                return;
            }

            try {
                applyState(await postForm(renameButton.dataset.url, {
                    name: nextName.trim(),
                    wins: nextWins.trim(),
                    target_wins: nextTarget.trim(),
                }));
            } catch (error) {
                handleAjaxError(error);
            }

            return;
        }

        if (deleteButton) {
            const list = document.querySelector("[data-game-list]");

            if (!window.confirm(list?.dataset.deleteConfirm || "Delete this game?")) {
                return;
            }

            try {
                applyState(await postForm(deleteButton.dataset.url, {}));
            } catch (error) {
                handleAjaxError(error);
            }
        }
    });

    document.addEventListener("submit", async (event) => {
        const deleteForm = event.target.closest(".js-confirm-delete");
        const addForm = event.target.closest("[data-game-add-form]");

        if (deleteForm && !window.confirm(deleteForm.dataset.confirmMessage)) {
            event.preventDefault();
            return;
        }

        if (!addForm) {
            return;
        }

        event.preventDefault();

        const formData = new FormData(addForm);
        const name = String(formData.get("name") || "").trim();
        const wins = String(formData.get("wins") || "").trim();
        const targetWins = String(formData.get("target_wins") || "").trim();

        if (!name || !targetWins) {
            return;
        }

        try {
            applyState(await postForm(addForm.action, { name, wins: wins || "0", target_wins: targetWins }));
            addForm.reset();
        } catch (error) {
            handleAjaxError(error);
        }
    });

    initEditor();
    initOverlayPolling();
    document.querySelectorAll("[data-winchallenge-overlay]").forEach(setupOverlayPager);
})();
