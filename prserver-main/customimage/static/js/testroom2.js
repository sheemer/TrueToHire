document.addEventListener('DOMContentLoaded', () => {
    const displayElement = document.querySelector('#guac-display');
    const errorContainer = document.querySelector('#error-message');
    const loadingSpinner = document.querySelector('#guac-loading');

    if (!displayElement) {
        console.error('Missing #guac-display element in DOM.');
        return;
    }

    const token = displayElement.dataset.token;
    const server = displayElement.dataset.server;
    const rawId = displayElement.dataset.identifier;
    const timeLimit = 60; // in minutes

    let client;
    let canvas;

    const extractId = (id) => {
        try {
            const decoded = atob(id);
            const match = decoded.match(/^\d+/);
            return match ? match[0] : null;
        } catch (error) {
            console.error('Failed to decode connId:', error);
            return null;
        }
    };

    const connId = extractId(rawId);
    if (!connId) {
        showError('Invalid connection ID.');
        return;
    }

    const initialize = () => {
        const tunnel = new Guacamole.HTTPTunnel(`${server}/guacamole/tunnel`);
        client = new Guacamole.Client(tunnel);
        canvas = client.getDisplay().getElement();
        document.querySelector('.guac-canvas-container').appendChild(canvas);
        const connectStart = Date.now();
        try {
            client.connect(`GUAC_ID=${connId}&GUAC_TYPE=c&GUAC_DATA_SOURCE=postgresql&token=${token}`);
        } catch (err) {
            console.error('Connection failed:', err);
            showError();
        }

        canvas.tabIndex = 1;
        canvas.style.outline = 'none';
        canvas.style.width = '100%';
        canvas.style.height = '100%';

        const mouse = new Guacamole.Mouse(canvas);
        mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = (state) => {
            client.sendMouseState(state);
        };

        const keyboard = new Guacamole.Keyboard(canvas);
        keyboard.onkeydown = (keysym) => {
            client.sendKeyEvent(1, keysym);
            return false;
        };
        keyboard.onkeyup = (keysym) => {
            client.sendKeyEvent(0, keysym);
            return false;
        };

        setTimeout(() => canvas.focus(), 500);
        canvas.addEventListener('click', () => canvas.focus());

        let reconnectCount = 0;
        const maxReconnects = 3;

        client.onstatechange = (state) => {
            console.log('Guacamole state:', state);
            if (state === 3) {
                const connectTime = Date.now() - connectStart;
                console.log(`Connected in ${connectTime}ms. Waiting for flush to scale display.`);
                loadingSpinner.style.display = 'none';
                errorContainer.style.display = 'none';
                reconnectCount = 0;
            } else if (state === 5 && reconnectCount < maxReconnects) {
                console.warn(`Disconnected. Attempting reconnect (${reconnectCount + 1}/${maxReconnects})...`);
                showError('Reconnecting...');
                reconnectCount++;
                setTimeout(() => {
                    try {
                        client.connect(`GUAC_ID=${connId}&GUAC_TYPE=c&GUAC_DATA_SOURCE=postgresql&token=${token}`);
                    } catch (err) {
                        console.error('Reconnect failed:', err);
                        showError();
                    }
                }, 3000);
            } else if (state === 5) {
                showError('Connection lost. Please refresh or contact support.');
            }
        };

        client.onerror = (error) => {
            console.error('Guacamole error:', error);
            showError();
        };

        // Flush is guaranteed when the remote display is rendered
        client.onflush = () => {
            const w = client.getDisplay().getWidth();
            const h = client.getDisplay().getHeight();
            if (w > 0 && h > 0) {
                console.log(`Flush received. Display size: ${w}x${h}`);
                requestAnimationFrame(() => scaleDisplay());
            }
        };

        window.addEventListener('resize', () => requestAnimationFrame(() => scaleDisplay()));
        window.addEventListener('beforeunload', () => client.disconnect());
    };

    window.reconnect = () => {
        if (client) client.disconnect();
        displayElement.innerHTML = `
            <div id="guac-loading" class="loading-spinner">{% trans "Connecting..." %}</div>
            <div id="error-message" class="error-message" style="display: none;"></div>
        `;
        initialize();
    };

    function scaleDisplay() {
        const display = client.getDisplay();
        const canvas = display.getElement();
        const container = document.querySelector('.guac-canvas-container');
    
        const nativeWidth = display.getWidth();
        const nativeHeight = display.getHeight();
    
        if (nativeWidth > 0 && nativeHeight > 0) {
            const containerWidth = container.clientWidth;
            const containerHeight = container.clientHeight;
    
            const scale = Math.min(
                containerWidth / nativeWidth,
                containerHeight / nativeHeight,
                1 // Never upscale beyond native resolution
            );
    
    
            display.scale(scale);
    
            canvas.style.width = `${nativeWidth * scale}px`;
            canvas.style.height = `${nativeHeight * scale}px`;
            canvas.style.maxHeight = '100vh'; // ensure it doesn’t overflow viewport
            canvas.style.maxWidth = '100vw';
    
            console.log(`Scaled canvas to ${canvas.style.width} x ${canvas.style.height} (scale: ${scale})`);
        } else {
            console.warn('Skipping scale: Display not ready.');
        }
    }
    
    const showError = (message = '{% trans "Failed to connect to the test environment." %}') => {
        loadingSpinner.style.display = 'none';
        errorContainer.style.display = 'block';
        errorContainer.textContent = message;
        if (canvas) canvas.style.display = 'none';
    };

    // Timer logic
    let timeRemaining = timeLimit * 60;
    const timeDisplay = document.querySelector('#time-remaining');
    const form = document.querySelector('#end-session');
    if (!timeDisplay || !form) {
        console.error('Timer or form element not found.');
    } else {
        const timerInterval = setInterval(() => {
            if (timeRemaining <= 0) {
                clearInterval(timerInterval);
                timeDisplay.textContent = '00:00';
                form.submit();
            } else {
                const minutes = Math.floor(timeRemaining / 60);
                const seconds = timeRemaining % 60;
                timeDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                timeRemaining--;
            }
        }, 1000);
    }

    initialize();
});
