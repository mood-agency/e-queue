// heartbeat_worker.js
let intervalId = null;

self.onmessage = function(e) {
    if (e.data.start && !intervalId) {
        intervalId = setInterval(() => {
            postMessage('heartbeat');
        }, e.data.interval);
    }
};