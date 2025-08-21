document.addEventListener("DOMContentLoaded", function () {
    const displayElement = document.getElementById("guac-display");
    const errorElement = document.getElementById("error-message");
    const loadingElement = document.getElementById("guac-loading");
    const token = displayElement.dataset.token;
    const server = displayElement.dataset.server;
    const rawConnId = displayElement.dataset.identifier;
    const timeLimit = parseInt(document.body.dataset.timeLimit, 10) || 60;
    const instructions = document.body.dataset.instructions || "{% trans 'No instructions provided.' %}";

    let client, guacCanvas;
    let lastInputTime = 0;

    // Extract connection ID
    function extractNumericId(connId) {
        try {
            const decoded = atob(connId);
            const match = decoded.match(/^\d+/);
            return match ? match[0] : null;
        } catch (e) {
            console.error("Failed to decode connId:", e);
            return null;
        }
    }
    const connId = extractNumericId(rawConnId);
    if (!connId) {
        showError("Invalid connection ID.");
        return;
    }

    // Initialize Guacamole
    function initializeGuacamole() {
        const tunnel = new Guacamole.HTTPTunnel(`${server}/guacamole/tunnel`);
        client = new Guacamole.Client(tunnel);
        guacCanvas = client.getDisplay().getElement();
        displayElement.appendChild(guacCanvas);

        // Connect
        let connectStartTime = Date.now();
        try {
            client.connect(`GUAC_ID=${connId}&GUAC_TYPE=c&GUAC_DATA_SOURCE=postgresql&token=${token}`);
        } catch (err) {
            console.error("Connection failed:", err);
            showError();
        }

        // Focus setup
        guacCanvas.tabIndex = 1;
        guacCanvas.style.outline = "none";
        guacCanvas.style.width = "100%";
        guacCanvas.style.height = "100%";

        // Mouse support
        const mouse = new Guacamole.Mouse(guacCanvas);
        let mouseEventQueue = [];
        let mouseFlushTimeout = null;
        function flushMouseEvents() {
            if (mouseEventQueue.length > 0) {
                const latestState = mouseEventQueue[mouseEventQueue.length - 1];
                client.sendMouseState(latestState);
                const latency = Date.now() - latestState.timestamp;
                console.log(`Mouse event sent, latency: ${latency}ms`);
                mouseEventQueue = [];
                mouseFlushTimeout = null;
            }
        }
        mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = function (mouseState) {
            mouseState.timestamp = Date.now();
            mouseEventQueue.push(mouseState);
            if (!mouseFlushTimeout) {
                mouseFlushTimeout = setTimeout(flushMouseEvents, 30);
            }
        };

        // Keyboard support
        const keyboard = new Guacamole.Keyboard(guacCanvas);
        let keyEventQueue = [];
        let keyFlushTimeout = null;
        function flushKeyEvents() {
            if (keyEventQueue.length > 0) {
                keyEventQueue.forEach(({ pressed, keysym, timestamp }) => {
                    client.sendKeyEvent(pressed, keysym);
                    const latency = Date.now() - timestamp;
                    console.log(`Key event sent, latency: ${latency}ms`);
                });
                keyEventQueue = [];
                keyFlushTimeout = null;
            }
        }
        keyboard.onkeydown = function (keysym) {
            keyEventQueue.push({ pressed: 1, keysym, timestamp: Date.now() });
            if (!keyFlushTimeout) {
                keyFlushTimeout = setTimeout(flushKeyEvents, 10);
            }
            return false;
        };
        keyboard.onkeyup = function (keysym) {
            keyEventQueue.push({ pressed: 0, keysym, timestamp: Date.now() });
            if (!keyFlushTimeout) {
                keyFlushTimeout = setTimeout(flushKeyEvents, 10);
            }
            return false;
        };

        // Focus canvas
        function focusCanvas() {
            guacCanvas.focus();
        }
        setTimeout(focusCanvas, 500);
        guacCanvas.addEventListener("click", focusCanvas);

        // State changes
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 3;
        client.onstatechange = function (state) {
            console.log("Guacamole state:", state);
            if (state === 3) { // Connected
                const connectTime = Date.now() - connectStartTime;
                console.log(`Connected in ${connectTime}ms. Scaling display.`);
                loadingElement.style.display = "none";
                errorElement.style.display = "none";
                setTimeout(() => requestAnimationFrame(scaleGuacDisplay), 1000);
                reconnectAttempts = 0;
            } else if (state === 5 && reconnectAttempts < maxReconnectAttempts) { // Disconnected
                console.warn(`Disconnected. Attempting reconnect (${reconnectAttempts + 1}/${maxReconnectAttempts})...`);
                showError("Reconnecting...");
                reconnectAttempts++;
                setTimeout(() => {
                    try {
                        connectStartTime = Date.now();
                        client.connect(`GUAC_ID=${connId}&GUAC_TYPE=c&GUAC_DATA_SOURCE=postgresql&token=${token}`);
                    } catch (err) {
                        console.error("Reconnect failed:", err);
                        showError();
                    }
                }, 3000);
            } else if (state === 5) {
                showError("Connection lost. Please refresh or contact support.");
            }
        };

        // Errors
        client.onerror = function (error) {
            console.error("Guacamole error:", error);
            showError();
        };

        // Resize handling
        const debouncedResize = function () {
            requestAnimationFrame(scaleGuacDisplay);
        };
        window.addEventListener("resize", debouncedResize);

        // Disconnect on unload
        window.addEventListener("beforeunload", () => client.disconnect());
    }

    // Manual reconnect
    window.reconnectGuacamole = function () {
        if (client) {
            client.disconnect();
        }
        displayElement.innerHTML = '<div id="guac-loading" class="loading-spinner">{% trans "Connecting..." %}</div><div id="error-message" class="error-message" style="display: none;"></div>';
        initializeGuacamole();
    };

    // Display scaling
    function scaleGuacDisplay(retryCount = 0) {
        const display = client.getDisplay();
        const container = displayElement;

        const width = window.innerWidth;
        const height = window.innerHeight;
        const nativeWidth = display.getWidth();
        const nativeHeight = display.getHeight();

        if (nativeWidth > 0 && nativeHeight > 0 && width > 0 && height > 0) {
            const scale = Math.min(1, Math.min(width / nativeWidth, height / nativeHeight));
            display.scale(scale);
            guacCanvas.style.width = "100%";
            guacCanvas.style.height = "100%";
            guacCanvas.style.position = "relative";
            guacCanvas.style.left = "0";
            guacCanvas.style.top = "0";
            console.log(`Scaled display: ${nativeWidth}x${nativeHeight} to ${width}x${height} at scale ${scale}`);
        } else if (retryCount < 20) {
            console.log(`Display or container size not ready (native: ${nativeWidth}x${nativeHeight}, container: ${width}x${height}), retrying scale...`);
            setTimeout(() => requestAnimationFrame(scaleGuacDisplay.bind(null, retryCount + 1)), 500);
        } else {
            console.warn("Failed to scale Guacamole display after multiple attempts.");
            showError("Failed to initialize display size.");
        }
    }

    // Show error message
    function showError(message = "{% trans 'Failed to connect to the test environment.' %}") {
        loadingElement.style.display = "none";
        errorElement.style.display = "block";
        errorElement.textContent = message;
        guacCanvas.style.display = "none";
    }

    // Timer logic
    let timeRemaining = timeLimit * 60;
    const timeDisplay = document.getElementById("time");
    const form = document.getElementById("end-session-form");
    if (!timeDisplay || !form) {
        console.error("Timer or form element not found.");
    } else {
        const timerInterval = setInterval(() => {
            if (timeRemaining <= 0) {
                clearInterval(timerInterval);
                timeDisplay.textContent = "00:00";
                form.submit();
            } else {
                const minutes = Math.floor(timeRemaining / 60);
                const seconds = timeRemaining % 60;
                timeDisplay.textContent = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
                timeRemaining--;
            }
        }, 1000);
    }

    // Instructions modal logic
    window.showInstructions = function (instructionsText) {
        const modal = document.getElementById("instructions-modal");
        const modalInstructions = document.getElementById("modal-instructions");
        modalInstructions.innerHTML = instructionsText || "{% trans 'No instructions provided.' %}";
        modal.style.display = "block";
        if (guacCanvas) guacCanvas.focus();
    };

    const closeModal = document.querySelector(".modal-close");
    if (closeModal) {
        closeModal.addEventListener("click", () => {
            document.getElementById("instructions-modal").style.display = "none";
            if (guacCanvas) guacCanvas.focus();
        });
    }

    // Close modal when clicking outside
    window.addEventListener("click", (event) => {
        const modal = document.getElementById("instructions-modal");
        if (event.target === modal) {
            modal.style.display = "none";
            if (guacCanvas) guacCanvas.focus();
        }
    });

    // Auto-show instructions
    if (instructions) {
        showInstructions(instructions);
    }

    // Initialize
    initializeGuacamole();
});