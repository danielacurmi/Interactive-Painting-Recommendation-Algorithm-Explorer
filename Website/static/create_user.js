/*
Handles client-side logic for:
- contacting backend
- redirecting existing users
- handling consent acceptance
- creating new user
*/
window.onload = function () {
    checkUser();
};

/* Call backend to check whether the current IP exists */
async function checkUser() {
    try {
        const response = await fetch('/api/check_user');
        const data = await response.json();

        if (data.exists === true) {
            // User already exists: redirect
            redirectToHome();
        } else {
            // New user: show consent form
            showConsentForm();
        }
    } catch (error) {
        console.error("Error checking user:", error);
    }
}

/* Display consent form */
function showConsentForm() {
    const loader = document.getElementById("loader");
    const modal = document.getElementById("consent-modal");

    if (loader) loader.style.display = "none";
    if (modal) modal.style.display = "flex";
}

/* Consent button click handler */
document.addEventListener("DOMContentLoaded", function () {
    const acceptButton = document.getElementById("accept-consent-btn");
    if (acceptButton) {
        acceptButton.addEventListener("click", acceptConsent);
    }
});

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
        }

    } catch (error) {
        console.error("Error creating session:", error);
    }
}

/* User clicks accept consent */
async function acceptConsent() {
    const checkbox = document.getElementById("consent-checkbox");
    const errorText = document.getElementById("consent-error");

    if (!checkbox.checked) {
         errorText.style.display = "block";
         return;
     }

    try {
        const response = await fetch('/api/create_user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const text = await response.text();
            console.error("Server error:", text);
            return;
        }
        const result = await response.json();
        
        if (result.success === true) {
            localStorage.setItem("user_id", result.user_id);
            await createSession();
            redirectToHome();
        }

    } catch (error) {
        console.error("Error creating user:", error);
    }
}

/* Redirect user to main page */
function redirectToHome() {
    window.location.href = "/index";
}

// Decline / Exit Button
document.addEventListener("DOMContentLoaded", function () {
    const declineButton = document.getElementById("decline-consent-btn");
    if (declineButton) {
        declineButton.addEventListener("click", declineConsent);
    }
});

async function declineConsent() {
    window.location.href = "/";
}

