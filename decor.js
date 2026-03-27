// Anime decorations: falling petals and stars
const decorContainer = document.getElementById('anime-decorations');

function createSakura() {
  const sakura = document.createElement('div');
  sakura.className = 'sakura';
  sakura.innerHTML = '🌸';
  sakura.style.left = Math.random() * 100 + 'vw';
  sakura.style.fontSize = (Math.random() * 10 + 10) + 'px';
  sakura.style.animationDuration = (Math.random() * 5 + 5) + 's';
  sakura.style.filter = `hue-rotate(${Math.random() * 50}deg)`;
  if (decorContainer) {
    decorContainer.appendChild(sakura);
  }
  setTimeout(() => sakura.remove(), 10000);
}

function createStar() {
  const star = document.createElement('div');
  star.className = 'floating-star';
  const size = Math.random() * 3 + 1;
  star.style.width = size + 'px';
  star.style.height = size + 'px';
  star.style.left = Math.random() * 100 + 'vw';
  star.style.top = Math.random() * 100 + 'vh';
  star.style.animationDelay = Math.random() * 2 + 's';
  if (decorContainer) {
    decorContainer.appendChild(star);
  }
}

// Boot decorations
document.addEventListener('DOMContentLoaded', () => {
  if (!decorContainer) return;
  // Initial stars
  for (let i = 0; i < 50; i++) createStar();
  // Periodically create sakura
  setInterval(createSakura, 1500);
});
