document.addEventListener("DOMContentLoaded", async () => {
    const boardButtons = document.querySelectorAll(".board");
    const finishBtn = document.querySelector(".btn");

    const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
    const appPath = (path) => `${BASE_PATH}${path}`;

    // If already a user no need to select boxes since user_profile has already been built
    const response1 = await fetch(appPath('/api/check_user'));
    const data1 = await response1.json();

    if (data1.exists === true) {
        redirectToHome();
    }

    let selected = new Set();

    function formatLabel(text) {
        return text
            .toLowerCase()
            .split(" ")
            .map(word =>
                word
                    .split("-")
                    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
                    .join("-")
            )
            .join(" ");
    }

    function formatPeriodLabel(label, start, end) {
        const formattedName = formatLabel(label);

        if (!start && !end) return formattedName;

        const endText = end === "Present" ? "Present" : end;

        return `${formattedName} \n(${start} – ${endText})`;
    }

    // Fetch box titles
    async function loadBoxes() {
        try {
            const response = await fetch(appPath("/api/get_box_titles"));
            const data = await response.json();

            if (!data.success) {
                console.error("Failed to load boxes:", data.error);
                return;
            }

            const boxes = data.boxes;

            // Fill UI boxes
            boardButtons.forEach((btn, index) => {
                if (index >= boxes.length) return;

                const box = boxes[index];

                // Store metadata on element
                btn.dataset.type = box.type;
                btn.dataset.label = box.label;
                if (box.meta) {
                    Object.keys(box.meta).forEach(key => {
                        btn.dataset[key] = box.meta[key];
                    });
                }

                // Set label
                const labelSpan = btn.querySelector(".board-label");
                if (box.type === "period") {
                    labelSpan.textContent = formatPeriodLabel(
                        box.label,
                        box.meta?.start,
                        box.meta?.end
                    );
                } else {
                    labelSpan.textContent = formatLabel(box.label);
                }
            });

        } catch (err) {
            console.error("Error fetching boxe titles:", err);
        }
    }

    // Handle selection
    function toggleSelection(btn) {
        const key = `${btn.dataset.type}:${btn.dataset.label}`;

        if (selected.has(key)) {
            selected.delete(key);
            btn.classList.remove("selected");
        } else {
            selected.add(key);
            btn.classList.add("selected");
        }

        // Enable button if >= 5 selections
        finishBtn.disabled = selected.size < 5;
    }

    // Attach click listeners
    boardButtons.forEach(btn => {
        btn.addEventListener("click", () => toggleSelection(btn));
    });

    // Button logic
    finishBtn.addEventListener("click", () => {
        if (selected.size < 5) return;

        // Convert selections into structured data
        const selectedData = Array.from(selected).map(item => {
            const [type, label] = item.split(":");
            return { type, label };
        });

        console.log("Selected preferences:", selectedData);

        // TODO: send to backend
        // fetch("/api/save_preferences", { ... })

        // Redirect or continue
        redirectToHome();
    });

    // Intitialise
    loadBoxes();
});

/* Redirect user to main page */
function redirectToHome() {
    const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
    window.location.href = `${BASE_PATH}/index`;
}