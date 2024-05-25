import time
from threading import Lock

import redis
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

# Set up a Redis connection pool
redis_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
redis_client = redis.Redis(connection_pool=redis_pool)

max_active_users = 2  # Limit of active users who can purchase tickets at once
user_timeout = {}  # Dictionary to track last heartbeat
timeout_lock = Lock()
timeout_duration = 20  # Timeout duration in seconds (e.g., 20 seconds)

# Initialize the scheduler with your Flask app's context
scheduler = BackgroundScheduler()
scheduler.start()


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    with timeout_lock:
        user_timeout[request.sid] = time.time()


@socketio.on('heartbeat')
def handle_heartbeat():
    with timeout_lock:
        user_timeout[request.sid] = time.time()


@socketio.on('register')
def handle_register(data):
    user_id = data['userId']
    session_id = request.sid
    with timeout_lock:
        user_timeout[session_id] = time.time()

    # Using Redis through the connection pool
    redis_client.hset('user_session_map', user_id, session_id)
    redis_client.hset('session_user_map', session_id, user_id)

    if not redis_client.sismember('connected_users', user_id):
        redis_client.sadd('connected_users', user_id)
        redis_client.rpush('user_queue', user_id)

    update_queue_positions(status='registered')


def update_queue_positions(status=None):
    all_users = redis_client.lrange('user_queue', 0, -1)
    for idx, uid_bytes in enumerate(all_users, 1):
        uid = uid_bytes.decode()
        session_id = redis_client.hget('user_session_map', uid)
        if session_id:
            new_position = 0 if idx <= max_active_users else idx - max_active_users
            socketio.emit('queue_update', {'position': new_position, 'status': status}, room=session_id.decode())


@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    with timeout_lock:
        if session_id in user_timeout:
            del user_timeout[session_id]
    cleanup_user_session(session_id)


def cleanup_user_session(session_id):
    user_id = redis_client.hget('session_user_map', session_id)
    if user_id:
        user_id = user_id.decode()
        redis_client.srem('connected_users', user_id)
        redis_client.lrem('user_queue', 0, user_id)
        redis_client.hdel('user_session_map', user_id)
        redis_client.hdel('session_user_map', session_id)
        update_queue_positions(status='disconnected')


def check_timeouts():
    with timeout_lock:
        current_time = time.time()
        to_cleanup = [sid for sid, last_time in user_timeout.items() if current_time - last_time > timeout_duration]
        for sid in to_cleanup:
            del user_timeout[sid]
            socketio.close_room(sid)
            handle_disconnect(sid)


# Add job to scheduler
scheduler.add_job(check_timeouts, 'interval', seconds=10)

if __name__ == '__main__':
    try:
        socketio.run(app, debug=True)
    finally:
        scheduler.shutdown()  # Properly shutdown the scheduler when app stops
