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

    const searchInput = document.querySelector("[data-dashboard-search-input]");
    const filterChips = document.querySelectorAll("[data-filter-type]");
    const sections = document.querySelectorAll("[data-dashboard-section]");
    const countEl = document.querySelector("[data-dashboard-count]");

    if (searchInput && filterChips.length && sections.length) {
        let activeType = "all";

        const setActiveChip = (type) => {
            activeType = type;
            filterChips.forEach((chip) => {
                const isActive = chip.dataset.filterType === type;
                chip.classList.toggle("is-active", isActive);
                chip.setAttribute("aria-pressed", String(isActive));
            });
        };

        const applyFilters = () => {
            const query = searchInput.value.trim().toLowerCase();
            let totalCards = 0;
            let shownCards = 0;

            sections.forEach((section) => {
                const typeMatches = activeType === "all" || section.dataset.dashboardSection === activeType;
                section.hidden = !typeMatches;

                if (!typeMatches) {
                    return;
                }

                const cards = section.querySelectorAll("[data-dashboard-name]");
                const noMatches = section.querySelector("[data-no-matches]");
                let visibleInSection = 0;

                cards.forEach((card) => {
                    totalCards += 1;
                    const matches = !query || card.dataset.dashboardName.includes(query);
                    card.hidden = !matches;
                    if (matches) {
                        visibleInSection += 1;
                        shownCards += 1;
                    }
                });

                if (noMatches) {
                    noMatches.hidden = cards.length === 0 || visibleInSection > 0;
                }
            });

            if (countEl) {
                const filtering = query !== "" || activeType !== "all";
                countEl.hidden = !filtering;
                if (filtering) {
                    countEl.textContent = countEl.dataset.countTemplate
                        .replace("{shown}", shownCards)
                        .replace("{total}", totalCards);
                }
            }
        };

        searchInput.addEventListener("input", applyFilters);

        filterChips.forEach((chip) => {
            chip.addEventListener("click", () => {
                setActiveChip(chip.dataset.filterType);
                applyFilters();
            });
        });

        document.querySelectorAll(".dashboard-jumps a").forEach((link) => {
            link.addEventListener("click", () => {
                if (activeType !== "all" || searchInput.value) {
                    searchInput.value = "";
                    setActiveChip("all");
                    applyFilters();
                }
            });
        });
    }

    const jumpLinks = document.querySelectorAll(".dashboard-jumps a");

    if (jumpLinks.length && sections.length && "IntersectionObserver" in window) {
        const setActiveJumpLink = (id) => {
            jumpLinks.forEach((link) => {
                const isActive = link.hash === `#${id}`;
                link.classList.toggle("is-active", isActive);
                if (isActive) {
                    link.setAttribute("aria-current", "true");
                } else {
                    link.removeAttribute("aria-current");
                }
            });
        };

        const sectionObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setActiveJumpLink(entry.target.id);
                    }
                });
            },
            { rootMargin: "-15% 0px -70% 0px", threshold: 0 },
        );

        sections.forEach((section) => sectionObserver.observe(section));
    }
})();
