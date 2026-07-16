(() => {
    const HISTORY_LIMIT = 50;
    const HISTORY_DELAY = 220;
    const AUTOSAVE_DELAY = 1100;

    const editableControls = (form) => Array.from(
        form.querySelectorAll("input, select, textarea"),
    ).filter((control) => (
        control.name
        && control.name !== "csrfmiddlewaretoken"
        && !["button", "submit", "reset", "file"].includes(control.type)
        && !control.matches("[data-editor-state-ignore]")
    ));

    const controlState = (control) => ({
        id: control.id || "",
        name: control.name,
        type: control.type,
        value: control.value,
        checked: ["checkbox", "radio"].includes(control.type) ? control.checked : undefined,
    });

    const initializeEditorState = (editor) => {
        const forms = Array.from(editor.querySelectorAll("[data-editor-state-form]"));
        const undoButton = editor.querySelector("[data-editor-undo]");
        const redoButton = editor.querySelector("[data-editor-redo]");
        const status = editor.querySelector("[data-editor-save-status]");
        const isCreate = editor.dataset.editorCreate === "true";
        const draftKey = editor.dataset.editorDraftKey || "";

        if (!forms.length || !undoButton || !redoButton || !status) {
            return;
        }

        const labels = {
            saved: editor.dataset.statusSaved || "All changes saved",
            unsaved: editor.dataset.statusUnsaved || "Unsaved changes",
            saving: editor.dataset.statusSaving || "Saving...",
            failed: editor.dataset.statusFailed || "Autosave failed",
            draftSaved: editor.dataset.statusDraftSaved || "Draft saved locally",
            draftRestored: editor.dataset.statusDraftRestored || "Local draft restored",
        };

        let history = [];
        let historyIndex = 0;
        let historyTimer;
        let applyingState = false;
        let allowNavigation = false;
        let dirty = false;
        let changeVersion = 0;
        let inFlightSaves = 0;
        const saveTimers = new Map();
        const savingForms = new Set();
        const queuedForms = new Set();
        const failedForms = new Set();

        const setStatus = (label, state) => {
            status.textContent = label;
            status.dataset.state = state;
        };

        const captureState = () => ({
            forms: forms.map((form, index) => ({
                key: form.dataset.editorFormKey || String(index),
                fields: editableControls(form).map(controlState),
            })),
        });

        const stateHash = (state) => JSON.stringify(state);

        const updateHistoryButtons = () => {
            undoButton.disabled = historyIndex <= 0;
            redoButton.disabled = historyIndex >= history.length - 1;
        };

        const persistDraft = (state) => {
            if (!draftKey) {
                return false;
            }

            try {
                localStorage.setItem(draftKey, JSON.stringify(state));
                return true;
            } catch {
                return false;
            }
        };

        const clearDraft = () => {
            if (!draftKey) {
                return;
            }

            try {
                localStorage.removeItem(draftKey);
            } catch {
                // Storage is optional; server-side autosave continues to work.
            }
        };

        const pushHistoryState = (state) => {
            if (history[historyIndex] && stateHash(history[historyIndex]) === stateHash(state)) {
                return;
            }

            history = history.slice(0, historyIndex + 1);
            history.push(state);

            if (history.length > HISTORY_LIMIT) {
                history.shift();
            }

            historyIndex = history.length - 1;
            updateHistoryButtons();
        };

        const flushHistory = () => {
            window.clearTimeout(historyTimer);
            historyTimer = undefined;
            const state = captureState();
            pushHistoryState(state);
            persistDraft(state);

            if (isCreate && dirty) {
                setStatus(labels.draftSaved, "draft");
            }
        };

        const restoreControl = (form, field) => {
            const controls = editableControls(form);
            const control = controls.find((candidate) => (
                field.id && candidate.id === field.id
            )) || controls.find((candidate) => (
                candidate.name === field.name && candidate.type === field.type
            ));

            if (!control) {
                return;
            }

            if (["checkbox", "radio"].includes(control.type)) {
                control.checked = Boolean(field.checked);
            } else {
                control.value = field.value;
            }
        };

        const applyState = (state) => {
            if (!state || !Array.isArray(state.forms)) {
                return false;
            }

            applyingState = true;

            state.forms.forEach((formState, index) => {
                const form = forms.find((candidate) => (
                    candidate.dataset.editorFormKey === formState.key
                )) || forms[index];

                if (!form || !Array.isArray(formState.fields)) {
                    return;
                }

                formState.fields.forEach((field) => restoreControl(form, field));
                form.dispatchEvent(new CustomEvent("nexora:editor-restore", {bubbles: true}));
            });

            applyingState = false;
            return true;
        };

        const maybeFinishAutosave = (savedVersion) => {
            if (
                inFlightSaves
                || saveTimers.size
                || failedForms.size
                || savedVersion !== changeVersion
            ) {
                return;
            }

            dirty = false;
            clearDraft();
            setStatus(labels.saved, "saved");
        };

        const saveForm = async (form) => {
            saveTimers.delete(form);

            if (savingForms.has(form)) {
                queuedForms.add(form);
                return;
            }

            flushHistory();
            const saveVersion = changeVersion;
            inFlightSaves += 1;
            savingForms.add(form);
            failedForms.delete(form);
            setStatus(labels.saving, "saving");

            try {
                const response = await fetch(form.dataset.autosaveUrl, {
                    method: "POST",
                    body: new FormData(form),
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                const payload = await response.json().catch(() => ({}));

                if (!response.ok || !payload.ok) {
                    throw new Error("Autosave failed");
                }
            } catch {
                failedForms.add(form);
                dirty = true;
                setStatus(labels.failed, "failed");
            } finally {
                inFlightSaves -= 1;
                savingForms.delete(form);

                if (queuedForms.delete(form)) {
                    saveTimers.set(form, window.setTimeout(() => saveForm(form), 0));
                }

                maybeFinishAutosave(saveVersion);
            }
        };

        const scheduleAutosave = (form) => {
            if (!form?.dataset.autosaveUrl) {
                return;
            }

            window.clearTimeout(saveTimers.get(form));
            failedForms.delete(form);
            saveTimers.set(form, window.setTimeout(() => saveForm(form), AUTOSAVE_DELAY));
        };

        const markChanged = (form) => {
            if (applyingState) {
                return;
            }

            dirty = true;
            changeVersion += 1;
            setStatus(labels.unsaved, "unsaved");
            window.clearTimeout(historyTimer);
            historyTimer = window.setTimeout(flushHistory, HISTORY_DELAY);
            scheduleAutosave(form);
        };

        const applyHistory = (nextIndex) => {
            if (nextIndex < 0 || nextIndex >= history.length || nextIndex === historyIndex) {
                return;
            }

            historyIndex = nextIndex;
            applyState(history[historyIndex]);
            updateHistoryButtons();
            if (isCreate && historyIndex === 0) {
                dirty = false;
                clearDraft();
                setStatus(labels.saved, "saved");
                return;
            }

            dirty = true;
            changeVersion += 1;
            persistDraft(captureState());

            if (isCreate) {
                setStatus(labels.draftSaved, "draft");
            } else {
                setStatus(labels.unsaved, "unsaved");
                forms.forEach(scheduleAutosave);
            }
        };

        const undo = () => {
            flushHistory();
            applyHistory(historyIndex - 1);
        };

        const redo = () => {
            flushHistory();
            applyHistory(historyIndex + 1);
        };

        forms.forEach((form) => {
            const onChange = () => markChanged(form);
            form.addEventListener("input", onChange);
            form.addEventListener("change", onChange);
            form.addEventListener("nexora:editor-change", onChange);
            form.addEventListener("submit", () => {
                allowNavigation = true;
                dirty = false;
                clearDraft();
            });
        });

        undoButton.addEventListener("click", undo);
        redoButton.addEventListener("click", redo);

        document.addEventListener("keydown", (event) => {
            if (!(event.ctrlKey || event.metaKey) || event.altKey) {
                return;
            }

            const activeElement = document.activeElement;
            if (activeElement && activeElement !== document.body && !editor.contains(activeElement)) {
                return;
            }

            const key = event.key.toLowerCase();
            const isUndo = key === "z" && !event.shiftKey;
            const isRedo = (key === "z" && event.shiftKey) || key === "y";

            if (!isUndo && !isRedo) {
                return;
            }

            event.preventDefault();
            if (isRedo) {
                redo();
            } else {
                undo();
            }
        });

        window.addEventListener("beforeunload", (event) => {
            if (!dirty || allowNavigation) {
                return;
            }

            event.preventDefault();
            event.returnValue = "";
        });

        const initialState = captureState();
        history = [initialState];
        historyIndex = 0;
        updateHistoryButtons();
        setStatus(labels.saved, "saved");

        if (draftKey) {
            try {
                const draft = JSON.parse(localStorage.getItem(draftKey) || "null");

                if (draft && stateHash(draft) !== stateHash(initialState) && applyState(draft)) {
                    history.push(captureState());
                    historyIndex = 1;
                    dirty = true;
                    changeVersion += 1;
                    updateHistoryButtons();
                    setStatus(labels.draftRestored, "draft");

                    if (!isCreate) {
                        forms.forEach(scheduleAutosave);
                    }
                }
            } catch {
                clearDraft();
            }
        }
    };

    document.querySelectorAll("[data-editor-state]").forEach(initializeEditorState);
})();
