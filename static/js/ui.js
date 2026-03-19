(function () {
    function normalize(text) {
        return (text || "").toLowerCase().trim();
    }

    document.querySelectorAll("[data-filter-input]").forEach((input) => {
        const targetSelector = input.dataset.filterTarget;
        const targetTextSelector = input.dataset.filterText || "";
        const targets = Array.from(document.querySelectorAll(targetSelector));

        input.addEventListener("input", function () {
            const query = normalize(input.value);

            targets.forEach((target) => {
                const textSource = targetTextSelector
                    ? target.querySelector(targetTextSelector)
                    : target;
                const haystack = normalize(textSource ? textSource.textContent : target.textContent);
                target.style.display = !query || haystack.includes(query) ? "" : "none";
            });
        });
    });

    document.querySelectorAll("[data-filter-select]").forEach((select) => {
        const targetSelector = select.dataset.filterTarget;
        const targetAttribute = select.dataset.filterAttribute;
        const targets = Array.from(document.querySelectorAll(targetSelector));

        select.addEventListener("change", function () {
            const selected = normalize(select.value);

            targets.forEach((target) => {
                const value = normalize(target.getAttribute(targetAttribute));
                target.style.display = !selected || selected === "all" || value === selected ? "" : "none";
            });
        });
    });
})();
