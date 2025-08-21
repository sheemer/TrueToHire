document.addEventListener('DOMContentLoaded', () => {
    // Mobile menu toggle
    const menuToggle = document.getElementById('menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');

    if (menuToggle && mobileMenu) {
        menuToggle.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });
    }

    // GSAP animations
    gsap.utils.toArray('.animate-in').forEach((el, i) => {
        gsap.fromTo(
            el,
            { opacity: 0, y: 30 },
            { 
                opacity: 1, 
                y: 0, 
                duration: 0.8, 
                delay: i * 0.2, 
                ease: 'power3.out',
                scrollTrigger: {
                    trigger: el,
                    start: 'top 80%',
                }
            }
        );
    });

    gsap.utils.toArray('.feature').forEach((el) => {
        el.addEventListener('mouseenter', () => {
            gsap.to(el, { scale: 1.03, rotation: 1, duration: 0.3, ease: 'power2.out' });
        });
        el.addEventListener('mouseleave', () => {
            gsap.to(el, { scale: 1, rotation: 0, duration: 0.3, ease: 'power2.out' });
        });
    });
});