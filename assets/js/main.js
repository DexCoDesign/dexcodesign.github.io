const nav = document.querySelector('.site-nav');

const updateNav = () => {
  nav?.classList.toggle('scrolled', window.scrollY > 32);
};

updateNav();
window.addEventListener('scroll', updateNav, { passive: true });

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});
