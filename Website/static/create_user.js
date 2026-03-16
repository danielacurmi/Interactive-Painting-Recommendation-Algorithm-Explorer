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
        const response = await fetch('/check_user');
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
    document.getElementById("loading-container").style.display = "none";
    document.getElementById("consent-container").style.display = "block";
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
        const response = await fetch('/create_user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();
        if (result.success === true) {

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