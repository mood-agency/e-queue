from threading import Lock
from time import time

from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, render_template, request
from flask_socketio import SocketIO
import redis
from apscheduler.schedulers.background import BackgroundScheduler

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
        self.user_timeout = {}
        self.lock = Lock()

    def update_heartbeat(self, session_id):
        with self.lock:
            self.user_timeout[session_id] = time()

    def remove_session(self, session_id):
        with self.lock:
            if session_id in self.user_timeout:
                del self.user_timeout[session_id]

    def check_timeouts(self):
        with self.lock:
            current_time = time()
            to_cleanup = [sid for sid, last_time in self.user_timeout.items() if
                          current_time - last_time > TIMEOUT_DURATION]
            for sid in to_cleanup:
                self.remove_session(sid)
                socketio.close_room(sid)
                self.cleanup_user_session(sid)


user_manager = UserManager()


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    user_manager.update_heartbeat(request.sid)


@socketio.on('heartbeat')
def handle_heartbeat():
    user_manager.update_heartbeat(request.sid)


@socketio.on('register')
def handle_register(data):
    user_id = data['userId']
    session_id = request.sid
    user_manager.update_heartbeat(session_id)

    with redis_client.pipeline() as pipe:
        pipe.hset('user_session_map', user_id, session_id)
        pipe.hset('session_user_map', session_id, user_id)
        if not redis_client.sismember('connected_users', user_id):
            pipe.sadd('connected_users', user_id)
            pipe.rpush('user_queue', user_id)
        pipe.execute()

    update_queue_positions()


@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    user_manager.remove_session(session_id)
    cleanup_user_session(session_id)


def cleanup_user_session(session_id):
    user_id = redis_client.hget('session_user_map', session_id)
    if user_id:
        user_id = user_id.decode()
        with redis_client.pipeline() as pipe:
            pipe.srem('connected_users', user_id)
            pipe.lrem('user_queue', 0, user_id)
            pipe.hdel('user_session_map', user_id)
            pipe.hdel('session_user_map', session_id)
            pipe.execute()
        update_queue_positions(status='disconnected')


def update_queue_positions(status=None):
    all_users = redis_client.lrange('user_queue', 0, -1)
    for idx, uid_bytes in enumerate(all_users, 1):
        uid = uid_bytes.decode()
        session_id = redis_client.hget('user_session_map', uid)
        if session_id:
            new_position = 0 if idx <= MAX_ACTIVE_USERS else idx - MAX_ACTIVE_USERS
            socketio.emit('queue_update', {'position': new_position, 'status': status}, room=session_id.decode())


# Create the interval trigger without misfire_grace_time
trigger = IntervalTrigger(seconds=10)

# Add the job to the scheduler with misfire_grace_time specified in the add_job call
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
