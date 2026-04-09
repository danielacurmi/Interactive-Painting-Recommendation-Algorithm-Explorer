document.addEventListener("DOMContentLoaded", async () => {
    await ensureUser();
});

document.addEventListener("DOMContentLoaded", () => {
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
            const response = await fetch(`/api/random-images/30`);
            const images = await response.json();
            fetching = false;
            return images.map(img => ({
                id: img.painting_id,
                url: `/${img.image_path}`
            }));
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

                try {
                    modalImage.dataset.id = img.dataset.id;
                    const response = await fetch(`/api/painting/${img.dataset.id}`);
                    if (!response.ok) throw new Error("Bad response");
                    const data = await response.json();
                    modalImage.src = `/${data.image_path}`;

                    const favButton = document.getElementById("addToFav");

                    // Reset the favourite button
                    favButton.innerHTML = '<i class="fa-regular fa-star"></i> Add to Favourites';
                    favButton.disabled = false;

                    title.textContent = data.title;

                    artist.textContent = data.artist.name_surname;

                    artistBirth.textContent =
                        `${data.artist.birth_year} – ${data.artist.death_year}, ${data.artist.nationality}`;

                    fields.textContent = `Fields: ${data.artist.fields}`;
                    artMovements.textContent = `Art Movements: ${data.artist.art_movements}`;
                    bio.textContent = data.artist.bio;

                    artStyle.textContent = `Art Style: ${data.art_style}`;
                    medium.textContent = `Medium: ${data.media}`;

                    year.textContent = `Year: ${data.year_created}`;
                    genre.textContent = `Genre: ${data.genre}`;

                    paletteType.textContent = `Palette Type: ${data.palette_type}`;
                    descriptionTags.textContent = `Description Tags: ${data.description_tags}`;

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
        closeModal.addEventListener("click", () => {
            modalOverlay.style.display = "none";
        });
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) modalOverlay.style.display = "none";
        });
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
});

const toast = document.getElementById('toast');
function showToast(message = 'Message', ms = 3500) {
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), ms);
}

// Ensure user exists and is stored in localStorage
async function ensureUser() {
    let userId = localStorage.getItem("user_id");

    // If already exists → reuse
    if (userId) return userId;

    try {
        const response = await fetch('/api/check_user');
        const data = await response.json();

        if (data.exists && data.user_id) {
            localStorage.setItem("user_id", data.user_id);
            return data.user_id;
        }

        // No user then must go to consent page
        window.location.href = "/";
        return null;

    } catch (err) {
        console.error("Error ensuring user:", err);
        return null;
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

    // Use the image source relative to the Flask server root
    const imageUrl = modalImage.src.replace(window.location.origin, "");

    try {
        const paintingId = modalImage.dataset.id;
        const userId = localStorage.getItem("user_id");

        const response = await fetch("/api/add-favourite", {
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
        } else {
            console.error("Failed to add favourite:", response.statusText);
            showToast("Failed to add favourite.");
        }
    } catch (err) {
        console.error("Error adding favourite:", err);
        showToast("An error occurred while adding to favourites.");
    }
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