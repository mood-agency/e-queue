// ticket-queue.js
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const container = document.createElement('div');
        document.body.appendChild(container);

        const script = document.createElement('script');
        script.src = 'https://cdn.socket.io/4.0.0/socket.io.min.js';
        script.onload = initializeQueue;
        document.head.appendChild(script);

        function initializeQueue() {
            let socket = io('', {
                reconnection: true,         // Enable automatic reconnection
                reconnectionAttempts: 3,    // Maximum number of reconnection attempts
                reconnectionDelay: 1000,    // Initial delay for reconnection (ms)
                reconnectionDelayMax: 5000, // Maximum delay for reconnection (ms)
                timeout: 20000              // Timeout for reconnection attempts (ms)
            });

            function getQueryParam(name) {
                const urlParams = new URLSearchParams(window.location.search);
                return urlParams.get(name);
            }

            socket.on('connect', function () {
                let userId = getQueryParam('id') || 'user_' + Math.random().toString(36).substr(2, 9);
                socket.emit('register', {userId: userId});
                console.log('Connected to the server with ID:', userId);

                // Start heartbeat worker
                const workerCode = `
                    let heartbeatInterval = null;

                    function sendHeartbeat() {
                        self.postMessage({ type: 'heartbeat' });
                    }

                    function startHeartbeat(interval) {
                        heartbeatInterval = setInterval(sendHeartbeat, interval);
                    }

                    function stopHeartbeat() {
                        clearInterval(heartbeatInterval);
                        self.close();
                    }

                    self.onmessage = function (event) {
                        if (event.data.type === 'start') {
                            startHeartbeat(event.data.interval);
                        } else if (event.data.type === 'stop') {
                            stopHeartbeat();
                        }
                    };
                `;
                const workerBlob = new Blob([workerCode], {type: 'application/javascript'});
                const workerUrl = URL.createObjectURL(workerBlob);
                const worker = new Worker(workerUrl);

                worker.onmessage = function (event) {
                    if (event.data.type === 'heartbeat') {
                        socket.emit('heartbeat');
                        let now = new Date();
                        let dateString = now.toLocaleDateString('en-GB', {
                            day: '2-digit', month: 'short', year: 'numeric'
                        }) + ' ' + now.toLocaleTimeString('en-GB', {
                            hour12: false,
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                            fractionalSecondDigits: 3
                        });
                        console.log('Heartbeat sent to the server at:', dateString);
                    }
                };
                worker.postMessage({type: 'start', interval: 10000});
            });

            socket.on('reconnect_attempt', () => {
                console.log('Attempting to reconnect to the server...');
            });

            socket.on('disconnect', function () {
                console.log('Disconnected from the server.');
                worker.postMessage({type: 'stop'});
            });

            socket.on('queue_update', function (data) {
                console.log('Queue update received:', data.position);

                if (data.position === 0) {
                    document.body.innerHTML = "<div id='info'></div>";
                    let positionElement = document.getElementById('info');
                    if (positionElement) {
                        positionElement.textContent = 'Buy your Ticket';
                    }

                } else {
                    document.body.innerHTML = '';

                    fetch('static/splash.html')
                        .then(response => response.text())
                        .then(html => {
                            document.body.innerHTML = html;

                            let positionElement = document.getElementById('queuePosition');
                            if (positionElement) {
                                positionElement.textContent = data.position;
                            }
                        })
                        .catch(error => {
                            console.error('Error loading the splash screen:', error);
                            document.body.textContent = 'Failed to load the splash screen.';
                        });
                }
            });
        }
    });
})();
