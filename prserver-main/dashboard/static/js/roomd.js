document.addEventListener('DOMContentLoaded', () => {
    const collapsibleButtons = document.querySelectorAll('.collapsible-btn');

    collapsibleButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Get the next sibling content div
            const content = button.nextElementSibling;

            // Check if this section is already open
            const isOpen = content.style.display === 'block';

            // Close all sections
            document.querySelectorAll('.content').forEach(c => {
                c.style.display = 'none';
            });
            document.querySelectorAll('.collapsible-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            // Open the clicked section if it wasn't already open
            if (!isOpen) {
                content.style.display = 'block';
                button.classList.add('active');
            }
        });
    });
});