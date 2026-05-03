document.addEventListener("DOMContentLoaded", async () => {
    const favContainer = document.getElementById("favourites-container");
    if (!favContainer) return; 

    const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
    const appPath = (path) => `${BASE_PATH}${path}`;

    try {
        const userId = localStorage.getItem("user_id");

        const response = await fetch(
            appPath(`/api/favourites?user_id=${userId}`)
        );

        const data = await response.json();
        const favourites = data.favourites;

        favourites.forEach(item => {
            const favCard = document.createElement("div");
            favCard.classList.add("favourite-card");

            const img = document.createElement("img");
            img.src = appPath(`/${item.image_path.replace(/^\/+/, "")}`);
            img.alt = "Favourite Painting";

            favCard.appendChild(img);
            favContainer.appendChild(favCard);
        });

    } catch (err) {
        console.error("Error loading favourites:", err);
    }
});

async function loadFavouritesBackground() {
  const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
  const appPath = (path) => `${BASE_PATH}${path}`;

  try {
    const userId = localStorage.getItem("user_id");

    const response = await fetch(
      appPath(`/api/favourites?user_id=${userId}`)
    );
    
    // Get last 4 (most recent)
    const data = await response.json();
    const favourites = data.favourites || [];
    const lastFour = favourites.slice(-4).reverse();

    const backgroundImages = lastFour
      .map(item => `url("${appPath(`/${item.image_path.replace(/^\/+/, "")}`)}")`)
      .join(', ');

    const favBoard = document.querySelector('.favourites-board');
    if (favBoard) {
      favBoard.style.backgroundImage = backgroundImages;
      favBoard.style.backgroundPosition = 'top left, top right, bottom left, bottom right';
      favBoard.style.backgroundSize = '50% 50%';
      favBoard.style.backgroundRepeat = 'no-repeat';
    }

  } catch (err) {
    console.error('Error loading favourites:', err);
  }
}

document.addEventListener('DOMContentLoaded', loadFavouritesBackground);
