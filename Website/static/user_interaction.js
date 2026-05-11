document.addEventListener("DOMContentLoaded", async () => {
    await initSession();
});

async function initSession() {
    const user_id = localStorage.getItem("user_id");
    if (!user_id) return;

    let session_id = localStorage.getItem("session_id");

    // Validate existing session
    if (session_id) {
        try {
            const res = await fetch(window.appPath("/api/validate_session"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id })
            });

            const data = await res.json();

            if (data.valid) {
                return; // still valid
            } else {
                localStorage.removeItem("session_id");
            }
        } catch (err) {
            console.error("Validation error:", err);
            localStorage.removeItem("session_id");
        }
    }

    // Create new session
    try {
        const response = await fetch(window.appPath("/api/get_session"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id })
        });

        const data = await response.json();

        if (data.success) {
            localStorage.setItem("session_id", data.session_id);
        }

    } catch (err) {
        console.error("Session init error:", err);
    }
}

function updateActivity() {
    const session_id = localStorage.getItem("session_id");
    if (!session_id) return;

    fetch(window.appPath("/api/update_activity"), {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ session_id })
    });
}

function debounce(func, delay) {
    let timeout;
    return function () {
        clearTimeout(timeout);
        timeout = setTimeout(func, delay);
    };
}

const activityEvents = ["click", "mousemove", "keydown", "scroll"];
activityEvents.forEach(event => {
    window.addEventListener(event, debounce(updateActivity, 5000));
});

function endSession() {
    const session_id = localStorage.getItem("session_id");
    if (!session_id) return;

    navigator.sendBeacon(
        window.appPath("/api/end_session"),
        JSON.stringify({ session_id })
    );

    localStorage.removeItem("session_id");
}

const weightsModal = document.getElementById("weightsModal");
const openBtn = document.getElementById("userWeights");
const closeBtn = document.getElementById("closeWeightsModal");

openBtn.addEventListener("click", () => {
    weightsModal.classList.remove("hidden");
});

closeBtn.addEventListener("click", () => {
    weightsModal.classList.add("hidden");
});

window.addEventListener("click", (e) => {
    if (e.target === weightsModal) {
        weightsModal.classList.add("hidden");
    }
});


const sliders = document.querySelectorAll(".slider-group input");
sliders.forEach(slider => {
    const valueLabel =
        document.getElementById(slider.id + "Value");

    valueLabel.textContent = slider.value;
    slider.addEventListener("input", () => {
        valueLabel.textContent = slider.value;
    });
});


// Save button
document.getElementById("saveWeightsBtn")
.addEventListener("click", () => {

    const weights = {
        rating: parseFloat(document.getElementById("ratingWeight").value),
        favourite: parseFloat(document.getElementById("favouriteWeight").value),
        not_interested: parseFloat(document.getElementById("notInterestedWeight").value),
        viewing_time: parseFloat(document.getElementById("viewingTimeWeight").value),
        click: parseFloat(document.getElementById("clickWeight").value),
        review: parseFloat(document.getElementById("reviewWeight").value),
        skip: parseFloat(document.getElementById("skipWeight").value)
    };

    console.log("Selected weights:", weights);

    // future:
    // send to backend API

    weightsModal.classList.add("hidden");
});