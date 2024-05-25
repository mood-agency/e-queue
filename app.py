import threading
from datetime import datetime
from threading import Lock
from time import time

import redis
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, render_template, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

# Set up a Redis connection pool and client
redis_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
redis_client = redis.Redis(connection_pool=redis_pool)

# Constants
MAX_ACTIVE_USERS = 2
TIMEOUT_DURATION = 20  # in seconds

# Scheduler
scheduler = BackgroundScheduler()
scheduler.start()


class UserManager:
    def __init__(self):
        self.lock = Lock()

    def update_heartbeat(self, session_id):
        # Store heartbeat time in Redis
        redis_client.set(f"heartbeat:{session_id}", time())

    def remove_session(self, session_id):
        # Remove session from Redis
        redis_client.delete(f"heartbeat:{session_id}")

    def check_timeouts(self):
        current_time = time()
        session_ids = redis_client.keys("heartbeat:*")
        to_cleanup = []
        for session_id in session_ids:
            session_id = session_id.decode().split(":")[1]
            last_time = float(redis_client.get(f"heartbeat:{session_id}"))
            if current_time - last_time > TIMEOUT_DURATION:
                to_cleanup.append(session_id)
        if to_cleanup:
            threading.Thread(target=self.cleanup_sessions, args=(to_cleanup,)).start()

    def cleanup_sessions(self, sessions):
        current_time = time()
        for session_id in sessions:
            last_time = float(redis_client.get(f"heartbeat:{session_id}") or 0)
            if current_time - last_time > TIMEOUT_DURATION:
                self.remove_session(session_id)
                socketio.close_room(session_id)
                cleanup_user_session(session_id)


def cleanup_user_session(session_id):
    user_id = redis_client.hget('user_mapping', f'session:{session_id}')
    if user_id:
        user_id = user_id.decode()
        with redis_client.pipeline() as pipe:
            pipe.lrem('user_queue', 0, user_id)
            pipe.hdel('user_mapping', f'user:{user_id}')
            pipe.hdel('user_mapping', f'session:{session_id}')
            pipe.execute()
        update_queue_positions(status='disconnected')


def update_queue_positions(status=None):
    all_users = redis_client.lrange('user_queue', 0, -1)
    for idx, uid_bytes in enumerate(all_users, 1):
        uid = uid_bytes.decode()
        session_id = redis_client.hget('user_mapping', f'user:{uid}')
        if session_id:
            new_position = 0 if idx <= MAX_ACTIVE_USERS else idx - MAX_ACTIVE_USERS
            print()
            socketio.emit('queue_update', {'position': new_position, 'status': status}, room=session_id.decode())


user_manager = UserManager()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/status')
def status():
    users_status = []
    all_users = redis_client.lrange('user_queue', 0, -1)
    for index, user_id in enumerate(all_users, start=1):
        user_id = user_id.decode()
        session_id = redis_client.hget('user_mapping', f'user:{user_id}')
        if session_id:
            session_id = session_id.decode()
            last_heartbeat = redis_client.get(f"heartbeat:{session_id}")
            if last_heartbeat:
                last_heartbeat = float(last_heartbeat.decode())
                formatted_heartbeat = datetime.fromtimestamp(last_heartbeat).strftime("%d %B %Y %H:%M:%S.%f")[:-3]
            else:
                last_heartbeat = 0  # Set last_heartbeat to 0 if not available
                formatted_heartbeat = "N/A"
        else:
            session_id = "N/A"
            last_heartbeat = 0  # Set last_heartbeat to 0 if not available
            formatted_heartbeat = "N/A"

        queue_position = index - MAX_ACTIVE_USERS if index > MAX_ACTIVE_USERS else 0

        users_status.append({
            "user_id": user_id,
            "session_id": session_id,
            "last_heartbeat": formatted_heartbeat,  # Use formatted_heartbeat instead of last_heartbeat
            "queue_position": queue_position
        })

    # Sort users_status based on queue_position in ascending order
    users_status.sort(key=lambda x: x["queue_position"])

    return render_template('status.html', users_status=users_status)


def save_heartbeat_data(user_id, timestamp):
    redis_client.hset(f"debug_heartbeats:{user_id}", timestamp, "received")


@socketio.on('connect')
def handle_connect():
    user_manager.update_heartbeat(request.sid)


@app.route('/api/queue_status/<user_id>')
def queue_status(user_id):
    # This should check if the session_id is in the queue
    queue_position = redis_client.hget('user_mapping', f'session:{user_id}')
    if queue_position:
        return {'in_queue': True, 'position': int(queue_position.decode())}, 200
    else:
        return {'in_queue': False}, 200


@socketio.on('heartbeat')
def handle_heartbeat():
    session_id = request.sid
    user_manager.update_heartbeat(session_id)

    user_id = redis_client.hget('user_mapping', f'session:{session_id}')
    if user_id:
        user_id = user_id.decode()
        timestamp = time()
        save_heartbeat_data(user_id, timestamp)


@socketio.on('register')
def handle_register(data):
    user_id = data['userId']
    session_id = request.sid
    user_manager.update_heartbeat(session_id)

    with redis_client.pipeline() as pipe:
        pipe.hset('user_mapping', f'user:{user_id}', session_id)
        pipe.hset('user_mapping', f'session:{session_id}', user_id)
        if not redis_client.hexists('user_mapping', f'user:{user_id}'):
            pipe.rpush('user_queue', user_id)
        pipe.execute()

    timestamp = time()
    save_heartbeat_data(user_id, timestamp)

    update_queue_positions()


@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    user_manager.remove_session(session_id)
    cleanup_user_session(session_id)


@app.route('/debug_heartbeats')
def debug_heartbeats():
    user_id = request.args.get('user_id')
    if user_id:
        heartbeat_data = redis_client.hgetall(f"debug_heartbeats:{user_id}")
        heartbeats = []
        for timestamp, status in heartbeat_data.items():
            timestamp = float(timestamp.decode())
            formatted_timestamp = datetime.fromtimestamp(timestamp).strftime("%d %B %Y %H:%M:%S.%f")[:-3]
            heartbeats.append({
                "timestamp": timestamp,
                "formatted_timestamp": formatted_timestamp,
                "status": status.decode()
            })

        # Sort heartbeats based on timestamp in descending order
        heartbeats.sort(key=lambda x: x["timestamp"], reverse=True)

        return render_template('debug_heartbeats.html', user_id=user_id, heartbeats=heartbeats)
    else:
        return "User ID not provided", 400


trigger = IntervalTrigger(seconds=10)
scheduler.add_job(
    user_manager.check_timeouts,
    trigger,
    coalesce=True,
    max_instances=1,
    misfire_grace_time=30  # 30 seconds grace period
)

if __name__ == '__main__':
    try:
        socketio.run(app, debug=True)
    finally:
        scheduler.shutdown()  # Ensure scheduler is properly shutdown when app stops
