# E-queue

e-queue is a python/redis scalable queue system that allows users to join a queue and be served in a
first-come-first-serve basis.

## Install

### Install Redis on Windows:
https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/install-redis-on-windows/

### Install Redis Insight(GUI):
https://redis.io/insight/?utm_source=redisinsight&utm_medium=website&utm_campaign=install_redisinsight#insight-form

## Run Redis Server
From WSL run:
`sudo service redis-server start`

## Run App Server
To run the server, you need to have the following installed:
`uvicorn app:app --host localhost --port 8000 --reload`

## Clone the repository and install the dependencies
Clone the repository and install the dependencies
`git clone https://github.com/mood-agency/e-queue.git`

`pip install -r requirements.txt`

`pip install flask-socketio`
`pip install eventlet`

### Development
`python app.py`

### Production
`gunicorn app:app --worker-class gevent --bind localhost:8000`

## Websocket and Worker connect and retry logic
```mermaid
graph TD
    A[Start] --> B[Load Socket.IO library]
    B --> C[Initialize Queue]
    C --> D[Connect to server]
    D -->|Error| R{Retry connection}
    R -->|Retry count <= max retries| D
    R -->|Retry count > max retries| S[Show connection error]
    D -->|Success| E[Register with server]
    E --> F[Create Web Worker]
    F --> G[Start heartbeat interval]
    G --> H{Heartbeat sent}
    H -->|Success| I[Log heartbeat sent]
    H -->|Error| J[Retry heartbeat send]
    J -->|Retry count <= max retries| G
    J -->|Retry count > max retries| K[Stop heartbeat]
    I --> L{Queue update received}
    K --> L
    L -->|Position = 0| M[No action]
    L -->|Position != 0| N[Update splash screen]
    N --> O[Fetch splash.html]
    O -->|Success| P[Update queue position]
    O -->|Error| Q[Show error message]
    P --> T{Disconnected from server}
    Q --> T
    T -->|Yes| U[Stop Web Worker]
    U --> V[Attempt to reconnect]
    V --> D
    S --> W[End]
```
## Splash Screen

Showed when the user get into the queue. You can modify the splash page by editing the `static/splash.html` file.

## Uploading Worker

### Set Up your Local Environment

`npm install -g @cloudflare/wrangler`
`wrangler login`

### Create your worker

`wrangler generate my-worker`
`cd my-worker`

### Configure Your Worker

Edit the wrangler.toml file in your project directory to specify your account details and settings:

* account_id: This can be found in your Cloudflare dashboard under the "Workers" tab.
* zone_id (optional): This is necessary if you are deploying your worker to a route associated with a specific domain.
* route (optional): If you want your worker to serve traffic for a specific route, specify it here.

```toml
name = "my-worker"
type = "javascript"

account_id = "your_account_id"
workers_dev = true  # Deploys to workers.dev subdomain; set to false if deploying to a custom route

# Uncomment and fill these out if deploying to a custom domain
# zone_id = "your_zone_id"
# route = "https://yourdomain.com/*"
```

### Preview and Test

`wrangler preview`

### Deploy

`wrangler publish`

## Debugging

### Queue status

To debug the queue status go to `http://localhost:5000/queue_status`

### Heartbeats

To debug the heartbeats go to `http://localhost:5000/debug_heartbeats?user_id=<user_id>`. You can find
the user_id in the queue status page.

