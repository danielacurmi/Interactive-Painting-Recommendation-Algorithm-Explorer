let isColdStartPhase = true;
let userConcepts = [];
const requestIdByPainting = {};
let hasUserInteracted = false;
let isSearchMode = false;
let searchResultsBuffer = [];
let useSbertMode = false;

document.addEventListener("DOMContentLoaded", async () => {
    await checkUser();
    await loadUserPreferences();
    await initRecommendations();
});

function initRecommendations() {
    let fetching = false;
    const container = document.getElementById('container');
    
    if (container) {
        const cols = Array.from(container.getElementsByClassName('col'));
        const modalOverlay = document.getElementById("modalOverlay");
        const modalImage = document.getElementById("modalImage");
        const closeModal = document.getElementById("closeModal");

        const fetchImageData = async () => {
            fetching = true;
            document.getElementById('loader').style.display = 'block';

            let images = [];

            try {
                if (isSearchMode) {
                    console.log("Using CLIP search results");
                    images = searchResultsBuffer;
                    if (images.length > 0) {
                        currentRequestId = images[0].request_id;
                    }
                    searchResultsBuffer = [];
                    return images.map(img => {
                        const id = img.painting_id;
                        requestIdByPainting[id] = img.request_id || currentRequestId;
                        return {
                            id: id,
                            url: img.image_url
                        };
                    });
                }
                
                const user_id = localStorage.getItem("user_id");
                const session_id = localStorage.getItem("session_id");

                if (!user_id || !session_id) {
                    console.error("Missing user/session id");
                    return;
                }

                // Initial set of recommendations
                if (isColdStartPhase) {
                    console.log("Fetching cold start images...");

                    const response = await fetch(window.appPath(`/api/cold-start-images`), {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            concepts: userConcepts,
                            user_id: parseInt(localStorage.getItem("user_id")),
                            session_id: parseInt(localStorage.getItem("session_id"))
                        })
                    });

                    const data = await response.json();

                    if (data.success && data.paintings) {
                        images = data.paintings;
                        currentRequestId = data.request_id;
                        isColdStartPhase = false; // switch to random after first batch
                    }
                } 
                // SBERT Recommendations
                else if (useSbertMode) {
                    console.log("Fetching recommendations using SBERT ...");

                    const user_id = localStorage.getItem("user_id");
                    const session_id = localStorage.getItem("session_id");

                    const response = await fetch(window.appPath(`/api/recommend_sbert`), {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            user_id: parseInt(user_id),
                            session_id: parseInt(session_id),
                            k: 20
                        })
                    });


                    const data = await response.json();

                    if (data.recommendations) {
                        images = data.recommendations;
                        currentRequestId = data.request_id;
                    } else {
                        console.error("No SBERT recommendations returned");
                        images = [];
                    }

                    console.log("SBERT response:", data);
                    console.log("SBERT recommendations length:", data.recommendations?.length);
                }
                // ResNet-50 Recommendations
                else {
                    if (!hasUserInteracted) {
                        console.log("Skipping recommender - no interactions yet");
                        return [];
                    }
                    console.log("Fetching recommendations using ResNet-50 ...");

                    const user_id = localStorage.getItem("user_id");
                    const session_id = localStorage.getItem("session_id");

                    const response = await fetch(window.appPath(`/api/recommend_resnet`), {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            user_id: parseInt(user_id),
                            session_id: parseInt(session_id),
                            k: 30
                        })
                    });

                    const data = await response.json();

                    if (data.recommendations) {
                        images = data.recommendations;
                        currentRequestId = data.request_id;
                    } else {
                        console.error("No recommendations returned");
                        images = [];
                    }
                }

            } catch (err) {
                console.error("Error fetching images:", err);
            }

            fetching = false;

            return images.map(img => {
                const id = img.painting_id;
                requestIdByPainting[id] = img.request_id || currentRequestId;

                return {
                    id: id,
                    url: img.image_url
                };
            });
        };

        const createCard = (imageData, col) => {
            const card = document.createElement('div');
            card.classList.add('card');

            const img = document.createElement('img');
            img.src = imageData.url;
            img.dataset.id = imageData.id;
            img.classList.add("clickable");

            img.onerror = function () {
                this.parentElement.style.display = "none";
            };
            img.onload = function () {
                document.getElementById('loader').style.display = 'none';
            };

            // Click to open image modal, uses data from backend app.py
            img.addEventListener("click", async () => {
                const paintingId = parseInt(img.dataset.id);
                const loader = document.getElementById('loader');
                const title = document.getElementById("modalTitle");
                const artist = document.getElementById("modalArtist");
                const artistBirth = document.getElementById("modalBirth");
                const artistDeath = document.getElementById("modalDeath");
                const nationality = document.getElementById("modalNationality");
                const fields = document.getElementById("modalFields");
                const artMovements = document.getElementById("modalartMovements");
                const bio = document.getElementById("modalBio"); 
                const year = document.getElementById("modalYear"); 
                const genre = document.getElementById("modalGenre");
                const artStyle = document.getElementById("modalArtStyle");
                const medium = document.getElementById("modalMedium");
                const descriptionTags = document.getElementById("modalDescriptionTags");
                const paletteType = document.getElementById("modalPaletteType");
                const paletteDiv = document.getElementById("paletteContainer");

                // Clear old content
                title.textContent = "";
                artist.textContent = "";
                artistBirth.textContent = "";
                artistDeath.textContent = "";
                nationality.textContent = "";
                fields.textContent = "";
                artMovements.textContent = "";
                bio.textContent = "";
                artStyle.textContent = "";
                medium.textContent = "";
                year.textContent = "";
                genre.textContent = "";
                paletteType.textContent = "";
                descriptionTags.textContent = "";
                paletteDiv.innerHTML = "";

                loader.style.display = 'block'; // Show loader only in details area

                // Show modal with the new image
                modalOverlay.style.display = "flex";
                document.body.classList.add("modal-open");
                console.log(`CLICK on painting ${paintingId}`);
                logInteraction(paintingId, "click", true);
                startViewing(paintingId)

                try {
                    modalImage.dataset.id = img.dataset.id;
                    const response = await fetch(window.appPath(`/api/painting/${img.dataset.id}`));
                    if (!response.ok) throw new Error("Bad response");
                    const data = await response.json();
                    modalImage.src = window.appPath(`/${String(data.image_path).replace(/^\/+/, "")}`);

                    const favButton = document.getElementById("addToFav");
                    const notIntButton = document.getElementById("notInterested");

                    // Reset the favourite and not interested button
                    favButton.innerHTML = '<i class="fa-regular fa-star"></i> Add to Favourites';
                    favButton.disabled = false;

                    notIntButton.innerHTML = '<i class="fa-sm fas fa-ban"></i> Not Interested';
                    notIntButton.disabled = false;

                    document.querySelectorAll('input[name="rate"]').forEach(radio => {
                        radio.checked = false;
                        radio.disabled = false;
                    });

                    setField(title, data.title);
                    setField(artist, data.artist?.name_surname);

                    setField(
                        artistBirth,
                        (data.artist?.birth_year || data.artist?.death_year || data.artist?.nationality)
                            ? `${data.artist?.birth_year ?? ""} – ${data.artist?.death_year ?? ""}, ${data.artist?.nationality ?? ""}`
                            : null
                    );

                    setField(fields, data.artist?.fields, "Fields: ");
                    setField(artMovements, data.artist?.art_movements, "Art Movements: ");
                    setField(bio, data.artist?.bio);

                    setField(artStyle, data.art_style, "Art Style: ");
                    setField(medium, data.media, "Medium: ");

                    setField(year, data.year_created, "Year: ");
                    setField(genre, data.genre, "Genre: ");

                    setField(paletteType, data.palette_type, "Palette Type: ");
                    setField(descriptionTags, data.description_tags, "Description Tags: ");

                    data.palette.forEach(color => {
                        const [r, g, b] = color;
                        const swatch = document.createElement("div");
                        swatch.classList.add("color-swatch");
                        swatch.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
                        paletteDiv.appendChild(swatch);
                    });
                } catch (err) {
                    console.error("Failed to fetch image info:", err);
                    title.textContent = "Error loading details";
                } finally {
                    loader.style.display = 'none'; // Hide loader when done
                }
            });

            card.appendChild(img);
            col.appendChild(card);
        };

        const loadImages = async () => {
            const images = await fetchImageData();
            if (images.length > 0) {
                images.forEach((imgData, index) => {
                    createCard(imgData, cols[index % cols.length]);
                });
            }
        };

        const handleScroll = () => {
            if (fetching) return;
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const windowHeight = window.innerHeight;
            const bodyHeight = document.documentElement.scrollHeight;
            if (bodyHeight - scrollTop - windowHeight < 800) {
                loadImages();
            }
        };

        loadImages(); 
        window.addEventListener('scroll', handleScroll);

        // Close modal
        // Close button
        closeModal.addEventListener("click", closeModalHandler);

        // Click outside modal
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) {
                closeModalHandler();
            }
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && modalOverlay.style.display === "flex") {
                closeModalHandler();
            }
        });

        window.switchRecommendationMode = async function (mode) {
            useSbertMode = false;
            isColdStartPhase = false;

            if (mode === "cold") {
                isColdStartPhase = true;
            }

            if (mode === "sbert") {
                useSbertMode = true;
                isColdStartPhase = false;
            }

            const container = document.getElementById("container");
            container.innerHTML = "";

            await loadImages();
        };
    }
    // Select both types of buttons and attach the same click behavior
    const buttons = Array.from(document.querySelectorAll('button.layered'));
    const board_buttons = Array.from(document.querySelectorAll('button.board'));
    const welcome_buttons = Array.from(document.querySelectorAll(".transparent-btn"));
    const allButtons = buttons.concat(board_buttons.concat(welcome_buttons));

    allButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active from the layered buttons collection so only one shows active
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const href = btn.dataset.href;
            if (href) {
                window.location.href = href;
            }
        });
    });
};

const toast = document.getElementById('toast');
function showToast(message = 'Message', ms = 3500) {
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), ms);
}

// Ensure user exists and is stored in localStorage
async function checkUser() {
    let userId = localStorage.getItem("user_id");
    const clientId = getOrCreateClientId();

    // If already mapped return
    if (userId && userId !== "null") return userId;

    try {
        const response = await fetch(window.appPath('/api/check_user'), {
            headers: {
                "X-User-ID": clientId
            }
        });

        const data = await response.json();

        if (data.exists && data.user_id) {
            localStorage.setItem("user_id", data.user_id);
            return data.user_id;
        }

        // No user exists
        return null;

    } catch (err) {
        console.error("Error ensuring user:", err);
        return null;
    }
}

// Track active viewing sessions per painting
const activeViews = {}; 
// { painting_id: start_timestamp }

// Logger
function logInteraction(painting_id, event_type, value = null) {
    const user_id = localStorage.getItem("user_id");
    const session_id = localStorage.getItem("session_id");

    const payload = {
        session_id: parseInt(session_id),
        user_id: parseInt(user_id),
        painting_id: parseInt(painting_id),
        event_type: event_type,
        value: value,
        request_id: requestIdByPainting[painting_id]
    };

    console.log("Sending event:", payload);

    fetch(appPath("/api/interaction_event_logging"), {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        console.log("Server response:", data);
    })
    .catch(err => {
        console.error("Logging error:", err);
    });
}

function startViewing(painting_id) {
    if (activeViews[painting_id]) return;
    activeViews[painting_id] = Date.now();
    console.log(`View START: ${painting_id}`);
    logInteraction(painting_id, "view_start");
}

function endViewing(painting_id) {
    if (!activeViews[painting_id]) return;
    console.log(`View END: ${painting_id}`);
    logInteraction(painting_id, "view_end");
    delete activeViews[painting_id];
}

document.querySelectorAll('input[name="rate"]').forEach(radio => {
    radio.addEventListener("change", function () {
        const rating = parseInt(this.value);
        // Disable all rating inputs
        document.querySelectorAll('input[name="rate"]').forEach(r => {
            r.disabled = true;
        });
        ratePainting(rating);
    });
});

async function ratePainting(rating) {
    const modalImage = document.getElementById("modalImage");
    if (!modalImage || !modalImage.dataset.id) {
        showToast("No image selected to rate.");
        return;
    }

    const paintingId = parseInt(modalImage.dataset.id);
    if (!rating || rating < 1 || rating > 5) {
        console.warn("Invalid rating:", rating);
        return;
    }

    console.log(`RATING: ${paintingId} -> ${rating}`);
    logInteraction(paintingId, "rating", rating);
    showToast(`Rated ${rating} stars!`);
}

async function submitReview() {
     // Get the image currently displayed in the modal
    const modalImage = document.getElementById("modalImage");
    if (!modalImage || !modalImage.src) {
        showToast("No image selected to submit areview.");
        return;
    }

    try {
        const paintingId = modalImage.dataset.id;
        const reviewInput = document.getElementById("review");
        const reviewText = reviewInput.value;
        console.log(`REVIEW: ${paintingId} - ${reviewText}`);
        logInteraction(paintingId, "review", reviewText);
        showToast("Review submitted!");
        reviewInput.value = "";

    } catch (err) {
        console.error("Review error:", err);
    }
}

async function markNotInterested() {
    // Get the image currently displayed in the modal
    const modalImage = document.getElementById("modalImage");
    if (!modalImage || !modalImage.src) {
        showToast("No image selected to mark as not interested.");
        return;
    }

    try {
        const paintingId = modalImage.dataset.id;
        console.log(`NOT INTERESTED: ${paintingId}`);
        logInteraction(paintingId, "not_interested", true);
        showToast("Marked as not interested... fewer paintings like this will be shown.");
        const btn = document.getElementById("notInterested");
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-sm fas fa-ban"></i> Marked';

    } catch (err) {
        console.error("Error marking not interested:", err);
        showToast("Something went wrong.");
    }
}

// Add to Favourites function
async function addToFavourites() {
    // Get the image currently displayed in the modal
    const modalImage = document.getElementById("modalImage");
    if (!modalImage || !modalImage.src) {
        showToast("No image selected to add to favourites.");
        return;
    }

    try {
        const paintingId = modalImage.dataset.id;
        const userId = localStorage.getItem("user_id");

        const response = await fetch(appPath("/api/add-favourite"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                painting_id: paintingId,
                user_id: userId
            }),
        });

        if (response.ok) {
            console.log("Added to favourites!");
            showToast("Painting added to favourites in create page!");

            const favButton = document.getElementById("addToFav");
            favButton.innerHTML = '<i class="fa-solid fa-star"></i> Added';
            favButton.disabled = true;
            logInteraction(paintingId, "favourite", true);
        } else {
            console.error("Failed to add favourite:", response.statusText);
            showToast("Failed to add favourite.");
        }
    } catch (err) {
        console.error("Error adding favourite:", err);
        showToast("An error occurred while adding to favourites.");
    }
}

function getOrCreateClientId() {
    let clientId = localStorage.getItem("client_id");

    if (!clientId) {
        clientId = crypto.randomUUID();
        localStorage.setItem("client_id", clientId);
    }

    return clientId;
}

async function loadUserPreferences() {
    hasUserInteracted = true;
    try {
        const response = await fetch(window.appPath("/api/get_user_preferences"), {
            headers: {
                "X-User-ID": localStorage.getItem("client_id")
            }
        });

        const data = await response.json();
        if (data.success && data.preferences) {
            userConcepts = data.preferences.map(pref => {
                if (pref.type && pref.label) {
                    return {
                        type: pref.type,
                        label: pref.label
                    };
                }
                if (pref.preference_type && pref.preference_label) {
                    return {
                        type: pref.preference_type,
                        label: pref.preference_label
                    };
                }
                if (Array.isArray(pref)) {
                    return {
                        type: pref[0],
                        label: pref[1]
                    };
                }
                console.warn("Unknown preference format:", pref);
                return null;
            }).filter(Boolean); 
        }
        console.log("Loaded concepts:", userConcepts);
    } catch (err) {
        console.error("Failed to load user preferences:", err);
    }
}

function closeModalHandler() {
    const paintingId = parseInt(modalImage.dataset.id);

    if (!isNaN(paintingId)) {
        endViewing(paintingId);
    }

    modalOverlay.style.display = "none";
    document.body.classList.remove("modal-open");
}

function setField(element, value, prefix = "") {
    if (value === null || value === undefined || value === "" || value === "null") {
        element.style.display = "none";
    } else {
        element.style.display = "block";
        element.textContent = prefix ? `${prefix}${value}` : value;
    }
}

const scrollBtn = document.getElementById("scrollTopBtn");

// Show button when scrolling down
window.addEventListener("scroll", () => {
    if (window.scrollY > 200) {
        scrollBtn.style.display = "block";
    } else {
        scrollBtn.style.display = "none";
    }
});

// Scroll to top
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}

// TRIPLE DOT drop down menu for explainability 
function showDropdown() {
    document.getElementById("myDropdown").classList.toggle("show");
}

// Close the dropdown if the user clicks outside of it
window.onclick = function(event) {
    if (!event.target.matches('.dropbtn')) {
        var dropdowns = document.getElementsByClassName("dropdown-content");
        var i;
        for (i = 0; i < dropdowns.length; i++) {
            var openDropdown = dropdowns[i];
            if (openDropdown.classList.contains('show')) {
                openDropdown.classList.remove('show');
            }
        }
    }
}

document.getElementById("exploreBtn").addEventListener("click", () => {
    window.switchRecommendationMode("sbert");
});

document.getElementById("homeBtn").addEventListener("click", () => {
    window.switchRecommendationMode("cold")
});

// Handle search bar input and log queries
async function handleSearchInput(event) {
    if (event.key === "Enter") {
        const query = event.target.value.trim();
        if (!query) return;

        try {
            const response = await fetch(window.appPath(`/api/search_clip`), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    user_id: parseInt(localStorage.getItem("user_id")),
                    session_id: parseInt(localStorage.getItem("session_id")),
                    request_id: crypto.randomUUID(),
                    query_text: query,
                    top_k: 20
                })
            });

            const data = await response.json();

            if (!data.success) throw new Error(data.error);
            showToast("Search query was submitted successfully!");

            // Activate search mode
            isSearchMode = true;
            searchResultsBuffer = data.recommendations;

            const container = document.getElementById('container');
            container.querySelectorAll('.col').forEach(col => col.innerHTML = "");

            // Load results into grid using existing pipeline
            loadImages();

        } catch (err) {
            console.error("Search failed:", err);
            showToast("An error occurred while trying to search.");
        }
    }
}

function clearSearch() {
    isSearchMode = false;
    searchResultsBuffer = [];

    const container = document.getElementById('container');
    container.querySelectorAll('.col').forEach(col => col.innerHTML = "");

    loadImages();
}

document.getElementById("searchBar").addEventListener("keydown", handleSearchInput);