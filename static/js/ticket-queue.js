// ticket-queue.js
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        // Create the necessary HTML elements
        const container = document.createElement('div');
        // container.innerHTML = `
        //     <h1>Welcome to the Ticket Queue!</h1>
        //     <p id="queuePosition">Waiting for queue update...</p>
        // `;
        document.body.appendChild(container);

        // Load the Socket.IO library
        const script = document.createElement('script');
        script.src = 'https://cdn.socket.io/4.0.0/socket.io.min.js';
        script.onload = initializeQueue;
        document.head.appendChild(script);

        function initializeQueue() {
            let socket = io();

            function getQueryParam(name) {
                const urlParams = new URLSearchParams(window.location.search);
                return urlParams.get(name);
            }

            socket.on('connect', function () {
                let userId = getQueryParam('id') || 'user_' + Math.random().toString(36).substr(2, 9);
                socket.emit('register', {userId: userId});
                console.log('Connected to the server with ID:', userId);

                // Create a Web Worker using a Blob and a data URL
                const workerCode = `
                    let heartbeatInterval = null;

                    self.onmessage = function (event) {
                        if (event.data.type === 'start') {
                            const interval = event.data.interval;
                            heartbeatInterval = setInterval(function () {
                                self.postMessage({ type: 'heartbeat' });
                            }, interval);
                        } else if (event.data.type === 'stop') {
                            clearInterval(heartbeatInterval);
                            self.close();
                        }
                    };
                `;
                const workerBlob = new Blob([workerCode], {type: 'application/javascript'});
                const workerUrl = URL.createObjectURL(workerBlob);
                const worker = new Worker(workerUrl);

                worker.onmessage = function (event) {
                    if (event.data.type === 'heartbeat') {
                        socket.emit('heartbeat');

                        // Create a new Date object
                        let now = new Date();

                        // Format the date and time
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

                // Stop the Web Worker on disconnect
                socket.on('disconnect', function () {
                    console.log('Disconnected from the server.');
                    worker.postMessage({type: 'stop'});
                    worker.terminate();
                });
            });

            socket.on('queue_update', function (data) {
                console.log('Queue update received:', data);

                if (data.position !== 0) {
                    // Clear the entire body content
                    document.body.innerHTML = '';

                    // Fetch the splash screen HTML and insert it
                    fetch('static/splash.html')
                        .then(response => response.text())
                        .then(html => {
                            document.body.innerHTML = html;

                            // Optionally, update part of the fetched HTML with the position
                            let positionElement = document.getElementById('queuePosition');
                            if (positionElement) {
                                positionElement.textContent = data.position;
                            }
                        })
                        .catch(error => {
                            console.error('Error loading the splash screen:', error);
                            // Fallback content if the fetch fails
                            document.body.textContent = 'Failed to load the splash screen.';
                        });
                }
            });
        }
    });
})();