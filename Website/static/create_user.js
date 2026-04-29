document.addEventListener("DOMContentLoaded", function () {
    checkUser();

    // Consent button click handler 
    const acceptButton = document.getElementById("accept-consent-btn");
    if (acceptButton) {
        acceptButton.addEventListener("click", acceptConsent);
    }
    
    // Decline / Exit to Welcome Page Button
    const declineButton = document.getElementById("decline-consent-btn");
    if (declineButton) {
        declineButton.addEventListener("click", declineConsent);
    }
});

const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
const appPath = (path) => `${BASE_PATH}${path}`;

// Check if client_id already exists in backend
async function checkUser() {
    try {
        const clientId = getOrCreateClientId();

        const response = await fetch(appPath('/api/check_user'), {
            headers: {
                "X-User-ID": clientId
            }
        });

        const data = await response.json();

        if (data.exists && data.user_id) {
            localStorage.setItem("user_id", data.user_id);
            redirectToNextPage();
        } else {
            // clear stale user_id
            localStorage.removeItem("user_id");
            showConsentForm();
        }

        console.log("client_id:", clientId);
        console.log("user_id (local):", localStorage.getItem("user_id"));
        console.log("backend response:", data);

    } catch (error) {
        console.error("Error checking user:", error);
    }
}

// Display consent form 
function showConsentForm() {
    const loader = document.getElementById("loader");
    const modal = document.getElementById("consent-modal");

    if (loader) loader.style.display = "none";
    if (modal) modal.style.display = "flex";
}

// User clicks accept consent 
async function acceptConsent() {
    const checkbox = document.getElementById("consent-checkbox");
    const errorText = document.getElementById("consent-error");

    if (!checkbox.checked) {
        errorText.style.display = "block";
        return;
    }

    try {
        const response = await fetch(appPath('/api/create_user'), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-User-ID": getOrCreateClientId()
            }
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("Server error:", data);
            return;
        }

        // Persist user_id
        if (data.success && data.user_id) {
            localStorage.setItem("user_id", data.user_id);
        }

        // Redirect after creation
        redirectToNextPage();

    } catch (error) {
        console.error("Error creating user:", error);
    }
}

async function declineConsent() {
    // Clear ALL identity state
    localStorage.removeItem("client_id");
    localStorage.removeItem("user_id");

    // Redirect to welcome
    window.location.href = appPath("/");
}

function getOrCreateClientId() {
    let clientId = localStorage.getItem("client_id");

    if (!clientId) {
        clientId = crypto.randomUUID();
        localStorage.setItem("client_id", clientId);
    }

    return clientId;
}

// Redirect user to cold start page 
function redirectToNextPage() {
    window.location.href = appPath("/cold_start"); 
}



