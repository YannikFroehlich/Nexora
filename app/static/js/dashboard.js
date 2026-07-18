(() => {
    const toast = document.querySelector("[data-copy-toast]");
    let toastTimer;

    const showToast = () => {
        if (!toast) {
            return;
        }

        toast.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => {
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

    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");

        if (!copyButton) {
            return;
        }

        try {
            await copyToClipboard(copyButton.dataset.copyUrl);
            showToast();
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
