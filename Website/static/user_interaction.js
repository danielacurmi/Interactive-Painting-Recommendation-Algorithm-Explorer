window.onload = function() {
    createSession();
};

window.addEventListener("pagehide", endSession);

const activityEvents = ["click", "mousemove", "keydown", "scroll"];
activityEvents.forEach(event => {
    window.addEventListener(event, debounce(updateActivity, 5000));
});

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

async function createSession() {
    const user_id = localStorage.getItem("user_id");

    if (!user_id) {
        console.error("No user_id found");
        return;
    }

    try {
        const response = await fetch(window.appPath('/api/create_session'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_id: user_id })
        });

        if (!response.ok) {
            const text = await response.text();
            console.error("Session error:", text);
            return;
        }

        const result = await response.json();

        if (result.success) {
            localStorage.setItem("session_id", result.session_id);
            console.log("Stored session_id:", result.session_id);
        }

    } catch (error) {
        console.error("Error creating session:", error);
    }
}

function endSession() {
    const session_id = localStorage.getItem("session_id");
    console.log("Ending session:", session_id);

    if (!session_id) {
        console.error("No session_id found");
        return;
    }
        
    try{
        navigator.sendBeacon(window.appPath("/api/end_session"),
        JSON.stringify({ session_id: session_id }));
        
        localStorage.removeItem("session_id");
    } catch (error) {
        console.error("Error ending session:", error);
    }
}

