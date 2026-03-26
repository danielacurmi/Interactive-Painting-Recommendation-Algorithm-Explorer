window.onload = function() {
    createSession();
};

window.addEventListener("pagehide", endSession);

async function createSession() {
    const user_id = localStorage.getItem("user_id");

    if (!user_id) {
        console.error("No user_id found");
        return;
    }

    try {
        const response = await fetch('/api/create_session', {
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
        navigator.sendBeacon("/api/end_session",
        JSON.stringify({ session_id: session_id }));
        
        localStorage.removeItem("session_id");
    } catch (error) {
        console.error("Error ending session:", error);
    }
}

