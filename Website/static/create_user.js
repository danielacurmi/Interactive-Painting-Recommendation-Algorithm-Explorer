window.onload = function () {
    checkUser();
};

const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
const appPath = (path) => `${BASE_PATH}${path}`;

/* Call backend to check whether the current IP exists */
async function checkUser() {
    try {
        const response = await fetch(appPath('/api/check_user'));
        const data = await response.json();
        localStorage.setItem("user_id", data.user_id);

        if (data.exists === true) {
            // User already exists: redirect
            redirectToNextPage();
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

/* User clicks accept consent */
async function acceptConsent() {
    const checkbox = document.getElementById("consent-checkbox");
    const errorText = document.getElementById("consent-error");

    if (!checkbox.checked) {
         errorText.style.display = "block";
         return;
     }

    try {
        const response = await fetch(appPath('/api/create_user'), {
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

    } catch (error) {
        console.error("Error creating user:", error);
    }
}

/* Redirect user to cold start page */
function redirectToNextPage() {
    window.location.href = appPath("/cold_start"); //cold_start
}

// Decline / Exit Button
document.addEventListener("DOMContentLoaded", function () {
    const declineButton = document.getElementById("decline-consent-btn");
    if (declineButton) {
        declineButton.addEventListener("click", declineConsent);
    }
});

async function declineConsent() {
    window.location.href = appPath("/");
}

