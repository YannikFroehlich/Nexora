(() => {
    const resizeDirections = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
    const arrowOffsets = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);

    const appendResizeHandles = (node, prefix) => {
        resizeDirections.forEach((direction) => {
            const handle = document.createElement("span");
            handle.className = `${prefix}-resize-handle ${prefix}-resize-handle--${direction}`;
            handle.dataset.resizeHandle = direction;
            handle.setAttribute("aria-hidden", "true");
            node.append(handle);
        });
    };

    // Moves (no direction) or resizes the box by dx/dy canvas pixels, snapped and kept on the canvas.
    const geometry = (box, direction, dx, dy, limits, snap) => {
        const right = box.x + box.width;
        const bottom = box.y + box.height;
        if (!direction) {
            return {
                ...box,
                x: clamp(snap(box.x + dx), 0, Math.max(limits.width - box.width, 0)),
                y: clamp(snap(box.y + dy), 0, Math.max(limits.height - box.height, 0)),
            };
        }

        const next = {...box};
        if (direction.includes("e")) {
            next.width = clamp(snap(right + dx), box.x + limits.minWidth, limits.width) - box.x;
        }
        if (direction.includes("w")) {
            next.x = clamp(snap(box.x + dx), 0, right - limits.minWidth);
            next.width = right - next.x;
        }
        if (direction.includes("s")) {
            next.height = clamp(snap(bottom + dy), box.y + limits.minHeight, limits.height) - box.y;
        }
        if (direction.includes("n")) {
            next.y = clamp(snap(box.y + dy), 0, bottom - limits.minHeight);
            next.height = bottom - next.y;
        }
        return next;
    };

    // Pointer drag, eight-direction resize and arrow-key nudging for absolutely positioned
    // canvas elements. The caller owns the element array, selection and rendering.
    const bind = ({
        canvas,
        elementSelector,
        findElement,
        bounds,
        scale,
        grid,
        minWidth = 24,
        minHeight = 8,
        onSelect = () => {},
        onMove = () => {},
        onEnd = () => {},
        onNudge = () => {},
        onDelete = null,
    }) => {
        const nodeFor = (id) => canvas.querySelector(
            `${elementSelector}[data-element-id="${CSS.escape(id)}"]`,
        );
        const snapper = () => {
            const {enabled, size} = grid();
            return enabled ? (value) => Math.round(value / size) * size : Math.round;
        };
        const boxOf = (element) => ({
            x: Number(element.x) || 0,
            y: Number(element.y) || 0,
            width: Number(element.width) || minWidth,
            height: Number(element.height) || minHeight,
        });

        canvas.addEventListener("pointerdown", (event) => {
            const node = event.target.closest(elementSelector);
            const element = node && event.button === 0 ? findElement(node.dataset.elementId) : null;
            if (!element) return;
            event.preventDefault();

            const direction = event.target.closest("[data-resize-handle]")?.dataset.resizeHandle || "";
            const origin = boxOf(element);
            onSelect(element);
            nodeFor(element.id)?.focus({preventScroll: true});
            const limits = {...bounds(), minWidth, minHeight};
            const factor = scale() || 1;
            const snap = snapper();
            let changed = false;

            const move = (moveEvent) => {
                const dx = Math.round((moveEvent.clientX - event.clientX) / factor);
                const dy = Math.round((moveEvent.clientY - event.clientY) / factor);
                if (dx || dy) changed = true;
                Object.assign(element, geometry(origin, direction, dx, dy, limits, snap));
                const current = nodeFor(element.id);
                if (current) {
                    Object.assign(current.style, {
                        left: `${element.x}px`,
                        top: `${element.y}px`,
                        width: `${element.width}px`,
                        height: `${element.height}px`,
                    });
                }
                onMove(element);
            };
            const end = () => {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", end);
                window.removeEventListener("pointercancel", end);
                onEnd(element, changed);
            };

            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", end);
            window.addEventListener("pointercancel", end);
        });

        canvas.addEventListener("keydown", (event) => {
            const node = event.target.closest(elementSelector);
            const element = node ? findElement(node.dataset.elementId) : null;
            if (!element) return;

            if (event.key === "Delete" && onDelete) {
                event.preventDefault();
                onDelete(element);
                return;
            }

            const offset = arrowOffsets[event.key];
            if (!offset) return;
            event.preventDefault();
            const {enabled, size} = grid();
            const step = enabled ? size * (event.shiftKey ? 5 : 1) : (event.shiftKey ? 10 : 1);
            Object.assign(element, geometry(
                boxOf(element),
                "",
                offset[0] * step,
                offset[1] * step,
                {...bounds(), minWidth, minHeight},
                snapper(),
            ));
            onNudge(element);
            // Rendering replaces the element nodes, so keep keyboard focus on the moved one.
            nodeFor(element.id)?.focus();
        });
    };

    window.NexoraCanvasEditor = {appendResizeHandles, bind};
})();
