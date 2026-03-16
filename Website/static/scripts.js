

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
                url: `/paintings/${img}`,
                filename: img
            }));
        };

        const createCard = (imageData, col) => {
            const card = document.createElement('div');
            card.classList.add('card');

            const img = document.createElement('img');
            img.src = imageData.url;
            img.dataset.filename = imageData.filename;
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
                const titleEl = document.getElementById("modalTitle");
                const artistEl = document.getElementById("modalArtist");
                const yearEl = document.getElementById("modalYear");
                const genreEl = document.getElementById("modalGenre");
                const paletteTypeEl = document.getElementById("modalPaletteType");
                const descriptionEl = document.getElementById("modalDescription");
                const paletteDiv = document.getElementById("paletteContainer");

                // Clear old content
                titleEl.textContent = "";
                artistEl.textContent = "";
                yearEl.textContent = "";
                genreEl.textContent = "";
                paletteTypeEl.textContent = "";
                descriptionEl.textContent = "";
                paletteDiv.innerHTML = "";

                loader.style.display = 'block'; // Show loader only in details area

                // Show modal with the new image
                modalImage.src = img.src;
                modalOverlay.style.display = "flex";

                try {
                    const response = await fetch(`/api/image-info/${img.dataset.filename}`);
                    if (!response.ok) throw new Error("Bad response");
                    const data = await response.json();

                    const favButton = document.getElementById("addToFav");

                    // Reset the favourite button
                    favButton.innerHTML = '<i class="fa-regular fa-star"></i> Add to Favourites';
                    favButton.disabled = false;

                    titleEl.textContent = `${data.painting_name}`;
                    artistEl.textContent = `By ${data.artist}`;
                    yearEl.textContent = `Year: ${data.year}`;
                    genreEl.textContent = `Genre: ${data.genre}`;
                    paletteTypeEl.textContent = `Palette Type: ${data.palette_type}`;
                    descriptionEl.textContent = `Description: ${data.description}`;

                    data.palette.forEach(color => {
                        const [r, g, b] = color;
                        const swatch = document.createElement("div");
                        swatch.classList.add("color-swatch");
                        swatch.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
                        paletteDiv.appendChild(swatch);
                    });
                } catch (err) {
                    console.error("Failed to fetch image info:", err);
                    titleEl.textContent = "Error loading details";
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
    const welcome_buttons = Array.from(document.querySelectorAll('transparent-btn'));
    const subButtons = buttons.concat(board_buttons);
    const allButtons = subButtons.concat(welcome_buttons);

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
        const response = await fetch("/api/add-favourite", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image: imageUrl }),
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



