(() => {
    // Free canvas for overlays whose content lives in fixed blocks ([data-element-id] wrappers).
    // Classic mode leaves the wrappers layout-neutral; custom mode positions them absolutely.
    const CUSTOM = "custom";

    const blocksOf = (root) => Array.from(root.querySelectorAll("[data-element-id]"));

    const apply = (root, mode, elements = [], editing = false) => {
        if (!root) return;
        root.dataset.layoutMode = mode === CUSTOM ? CUSTOM : "classic";
        const byId = new Map((Array.isArray(elements) ? elements : []).map((element) => [element.id, element]));
        blocksOf(root).forEach((block) => {
            const element = mode === CUSTOM ? byId.get(block.dataset.elementId) : null;
            block.style.left = element ? `${element.x}px` : "";
            block.style.top = element ? `${element.y}px` : "";
            block.style.width = element ? `${element.width}px` : "";
            block.style.height = element ? `${element.height}px` : "";
            const hidden = Boolean(element) && element.visible === false;
            // The editor keeps hidden blocks grabbable; the overlay drops them.
            block.style.display = hidden && !editing ? "none" : "";
            block.classList.toggle("is-layout-hidden", hidden && editing);
        });
    };

    const scaleOf = (root) => root.getBoundingClientRect().width / (root.offsetWidth || 1);

    // Boxes of the blocks as currently rendered, relative to the canvas padding box.
    const measure = (root) => {
        const scale = scaleOf(root) || 1;
        const rootRect = root.getBoundingClientRect();
        return blocksOf(root).map((block) => {
            const target = getComputedStyle(block).display === "contents" ? block.firstElementChild : block;
            const rect = target?.getBoundingClientRect();
            const visible = Boolean(rect && rect.width && rect.height);
            const x = visible ? (rect.left - rootRect.left) / scale - root.clientLeft : 0;
            const y = visible ? (rect.top - rootRect.top) / scale - root.clientTop : 0;
            return {
                id: block.dataset.elementId,
                x: Math.max(Math.round(x), 0),
                y: Math.max(Math.round(y), 0),
                width: visible ? Math.max(Math.round(rect.width / scale), 20) : 120,
                height: visible ? Math.max(Math.round(rect.height / scale), 8) : 32,
                visible: true,
            };
        });
    };

    const bindEditor = (controls) => {
        const form = controls.closest("form");
        const root = document.querySelector(controls.dataset.layoutRoot);
        const modeInput = form?.querySelector("[data-layout-mode-field]");
        const elementsInput = form?.querySelector("[data-layout-elements]");
        const heightInput = controls.dataset.layoutHeightField
            ? document.getElementById(controls.dataset.layoutHeightField)
            : null;
        if (!form || !root || !modeInput || !elementsInput || !window.NexoraCanvasEditor) return null;

        const parse = () => {
            try {
                const value = JSON.parse(elementsInput.value || "[]");
                return Array.isArray(value) ? value : [];
            } catch {
                return [];
            }
        };
        let elements = parse();
        let selectedId = null;
        const isCustom = () => modeInput.value === CUSTOM;
        const sync = () => { elementsInput.value = JSON.stringify(elements); };
        const notify = () => {
            sync();
            form.dispatchEvent(new CustomEvent("nexora:editor-change", {bubbles: true}));
        };

        const render = () => {
            apply(root, modeInput.value, elements, true);
            root.querySelectorAll("[data-element-id] > [data-resize-handle]").forEach((handle) => handle.remove());
            blocksOf(root).forEach((block) => {
                const selected = isCustom() && block.dataset.elementId === selectedId;
                block.classList.toggle("is-selected", selected);
                if (isCustom()) block.tabIndex = 0;
                else block.removeAttribute("tabindex");
                if (selected) window.NexoraCanvasEditor.appendResizeHandles(block, "layout");
            });
            controls.querySelectorAll("[data-layout-visibility]").forEach((checkbox) => {
                const element = elements.find((item) => item.id === checkbox.dataset.layoutVisibility);
                checkbox.checked = element?.visible !== false;
                checkbox.disabled = !isCustom();
            });
            controls.querySelectorAll("[data-layout-custom-only]").forEach((node) => { node.hidden = !isCustom(); });
        };

        // Start the free canvas exactly where the classic layout put each block, measured
        // at the canvas width (the classic preview may be narrower).
        const seedFromClassic = () => {
            const visibility = new Map(elements.map((element) => [element.id, element.visible]));
            apply(root, CUSTOM, [], true);
            const canvasWidth = root.offsetWidth;
            apply(root, "classic", [], true);
            root.style.width = `${canvasWidth}px`;
            elements = measure(root).map((element) => ({
                ...element,
                visible: visibility.get(element.id) !== false,
            }));
            const contentBottom = Math.max(...elements.map((element) => element.y + element.height))
                + (Number.parseFloat(getComputedStyle(root).paddingBottom) || 0);
            const naturalHeight = root.offsetHeight;
            root.style.width = "";
            // A canvas without a fixed height needs one that fits every block.
            if (heightInput && !(Number.parseInt(heightInput.value, 10) > 0)) {
                heightInput.value = String(Math.ceil(Math.max(naturalHeight, contentBottom)));
                heightInput.dispatchEvent(new Event("input", {bubbles: true}));
            }
        };

        modeInput.addEventListener("change", () => {
            if (isCustom() && elements.length !== blocksOf(root).length) seedFromClassic();
            render();
            notify();
        });
        controls.querySelector("[data-layout-reset]")?.addEventListener("click", () => {
            seedFromClassic();
            render();
            notify();
        });
        controls.querySelectorAll("[data-layout-visibility]").forEach((checkbox) => {
            checkbox.addEventListener("change", () => {
                const element = elements.find((item) => item.id === checkbox.dataset.layoutVisibility);
                if (!element) return;
                element.visible = checkbox.checked;
                render();
                notify();
            });
        });
        form.addEventListener("nexora:editor-restore", () => {
            elements = parse();
            render();
        });

        window.NexoraCanvasEditor.bind({
            canvas: root,
            elementSelector: "[data-element-id]",
            findElement: (id) => (isCustom() ? elements.find((element) => element.id === id) : null),
            bounds: () => ({width: root.clientWidth, height: root.clientHeight}),
            scale: () => scaleOf(root),
            grid: () => ({enabled: false, size: 10}),
            minWidth: 20,
            minHeight: 8,
            onSelect: (element) => { selectedId = element.id; render(); },
            onMove: sync,
            onEnd: (element, changed) => { if (changed) notify(); },
            onNudge: (element) => { selectedId = element.id; render(); notify(); },
        });

        render();
        return {render};
    };

    document.querySelectorAll("[data-layout-controls]").forEach(bindEditor);
    window.NexoraLayout = {apply};
})();
