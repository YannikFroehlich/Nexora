(() => {
    const FONT_FAMILY = "NexoraUploadedOverlayFont";
    const FONT_STYLE_ID = "nexora-uploaded-overlay-font";
    const FONT_STACKS = Object.freeze({
        system: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        arial: "Arial, sans-serif",
        verdana: "Verdana, sans-serif",
        trebuchet: "'Trebuchet MS', sans-serif",
        georgia: "Georgia, serif",
        times: "'Times New Roman', serif",
        courier: "'Courier New', monospace",
    });

    const brandingState = (state = {}) => state.design || state;

    const safeAssetUrl = (value) => {
        if (!value) return "";
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? url.href : "";
        } catch {
            return "";
        }
    };

    const applyFont = (root, fontUrl, fontFamily) => {
        let style = document.getElementById(FONT_STYLE_ID);
        if (!fontUrl) {
            style?.remove();
            root.style.setProperty(
                "--nexora-overlay-font",
                FONT_STACKS[fontFamily] || FONT_STACKS.system,
            );
            return;
        }

        if (!style) {
            style = document.createElement("style");
            style.id = FONT_STYLE_ID;
            document.head.append(style);
        }
        style.textContent = `@font-face { font-family: "${FONT_FAMILY}"; src: url("${fontUrl}"); font-display: swap; }`;
        root.style.setProperty("--nexora-overlay-font", `"${FONT_FAMILY}"`);
    };

    const applyLogo = (root, logoUrl) => {
        let logo = root.querySelector(":scope > [data-overlay-custom-logo]");
        if (!logoUrl) {
            logo?.remove();
            return;
        }
        if (!logo) {
            logo = document.createElement("img");
            logo.alt = "";
            logo.dataset.overlayCustomLogo = "";
            logo.className = "overlay-custom-logo";
            root.prepend(logo);
        }
        logo.src = logoUrl;
    };

    const apply = (root, state = {}) => {
        if (!root) return;
        const branding = brandingState(state);
        const fontUrl = safeAssetUrl(branding.font_url);
        const fontFamily = branding.font_family || "system";
        const logoUrl = safeAssetUrl(branding.logo_url);
        const backgroundUrl = safeAssetUrl(branding.background_image_url);

        applyFont(root, fontUrl, fontFamily);
        applyLogo(root, logoUrl);
        if (backgroundUrl) {
            root.style.setProperty("--nexora-overlay-background-image", `url("${backgroundUrl}")`);
        } else {
            root.style.removeProperty("--nexora-overlay-background-image");
        }
    };

    const selectedAssetUrl = (editor, fieldName) => {
        const field = editor.querySelector(`[data-branding-field="${fieldName}"]`);
        return field?.selectedOptions?.[0]?.dataset.assetUrl || "";
    };

    const applyEditorSelection = (editor) => {
        const root = editor.querySelector("[data-overlay-branding-root]");
        apply(root, {
            font_family: editor.querySelector("[data-branding-font-family]")?.value || "system",
            font_url: selectedAssetUrl(editor, "font_asset"),
            logo_url: selectedAssetUrl(editor, "logo_asset"),
            background_image_url: selectedAssetUrl(editor, "background_asset"),
        });
    };

    document.querySelectorAll("[data-overlay-branding-editor]").forEach((editor) => {
        editor.querySelectorAll("[data-branding-field], [data-branding-font-family]").forEach((field) => {
            field.addEventListener("change", () => applyEditorSelection(editor));
        });
        editor.addEventListener("nexora:editor-restore", () => applyEditorSelection(editor));
        applyEditorSelection(editor);
    });

    window.NexoraBranding = {apply};
})();
