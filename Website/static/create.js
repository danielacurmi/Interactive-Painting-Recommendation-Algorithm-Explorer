document.addEventListener("DOMContentLoaded", async () => {
    const favContainer = document.getElementById("favourites-container");
    if (!favContainer) return; 

    try {
        const response = await fetch("/api/favourites");
        const favourites = await response.json();

        favourites.forEach(image => {
            const favCard = document.createElement("div");
            favCard.classList.add("favourite-card");

            const img = document.createElement("img");
            img.src = image;
            img.alt = "Favourite Painting";

            favCard.appendChild(img);
            favContainer.appendChild(favCard);
        });
    } catch (err) {
        console.error("Error loading favourites:", err);
    }
});


async function loadFavouritesBackground() {
  try {
    const response = await fetch('/api/favourites');
    const data = await response.json();

    // `data` is already an array
    const favourites = data.slice(-4).reverse();

    const backgroundImages = favourites
      .map(url => `url("${url}")`)
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
