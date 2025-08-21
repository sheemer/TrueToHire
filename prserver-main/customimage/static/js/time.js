        document.addEventListener("DOMContentLoaded", () => {
            const publicId = document.body.dataset.publicId;
            setTimeout(() => {
                window.location.href = `/customimage/test-room/${publicId}/`;
            }, 120000);
        });