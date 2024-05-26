import os
import threading
from datetime import datetime
from threading import Lock
from time import time

import redis
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, disconnect, emit

app = Flask(__name__)
socketio = SocketIO(app)

load_dotenv()
# Constants
MAX_ACTIVE_USERS = os.getenv('MAX_ACTIVE_USERS')
TIMEOUT_DURATION = os.getenv('TIMEOUT_DURATION')  # in seconds
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = os.getenv('REDIS_PORT')
REDIS_DB = os.getenv('REDIS_DB')

# Set up a Redis connection pool and client
redis_pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
redis_client = redis.Redis(connection_pool=redis_pool)

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
    # Directly call the api_status function and get the JSON data
    response = api_status()  # This is a Flask Response object
    users_status = response.get_json()  # Extract JSON data from response

    # Now pass this data to your template
    return render_template('status.html', users_status=users_status)


def save_heartbeat_data(user_id, timestamp):
    redis_client.hset(f"debug_heartbeats:{user_id}", timestamp, "received")


@socketio.on('connect')
def handle_connect():
    user_manager.update_heartbeat(request.sid)


@app.route('/api/status')
def api_status():
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
                formatted_heartbeat = "N/A"
        else:
            session_id = "N/A"
            formatted_heartbeat = "N/A"

        queue_position = index - MAX_ACTIVE_USERS if index > MAX_ACTIVE_USERS else 0

        users_status.append({
            "user_id": user_id,
            "session_id": session_id,
            "last_heartbeat": formatted_heartbeat,
            "queue_position": queue_position
        })

    return jsonify(users_status)


@app.route('/api/debug_heartbeats')
def api_debug_heartbeats():
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

        return jsonify(heartbeats)
    return jsonify({"error": "User ID not provided"}), 400


@app.route('/api/user_session_active/<user_id>')
def user_session_active(user_id):
    session_id = redis_client.hget('user_mapping', f'user:{user_id}')
    if session_id:
        session_id = session_id.decode()
        last_heartbeat = redis_client.get(f"heartbeat:{session_id}")
        if last_heartbeat:
            last_heartbeat = float(last_heartbeat)
            current_time = time()
            if (current_time - last_heartbeat) <= TIMEOUT_DURATION:
                return {'user_id': user_id, 'session_id': session_id, 'active': True}, 200
            else:
                return {'user_id': user_id, 'session_id': session_id, 'active': False}, 200
        else:
            # No heartbeat found, consider session inactive
            return {'user_id': user_id, 'session_id': session_id, 'active': False}, 200
    else:
        # No session found for this user
        return {'user_id': user_id, 'session_id': 'N/A', 'active': False}, 200


@app.route('/api/queue_status/<session_id>')
def queue_status(session_id):
    # This should check if the session_id is in the queue
    queue_position = redis_client.hget('user_mapping', f'session:{session_id}')
    if queue_position:
        return {'in_queue': True, 'position': int(queue_position.decode())}, 200
    else:
        return {'in_queue': False}, 200


@app.route('/debug_heartbeats')
def debug_heartbeats():
    # Get user_id from request parameters
    user_id = request.args.get('user_id')
    if user_id:
        # Call the API function directly
        api_response = api_debug_heartbeats()  # This should return a Flask Response object
        if api_response.status_code == 200:
            heartbeats = api_response.get_json()  # Extract JSON data from the response
            return render_template('debug_heartbeats.html', user_id=user_id, heartbeats=heartbeats)
        else:
            # Handle possible errors or no data found
            return render_template('debug_heartbeats.html', user_id=user_id, heartbeats=[], error="No data found.")
    else:
        return "User ID not provided", 400


@socketio.on('heartbeat')
def handle_heartbeat():
    session_id = request.sid
    user_manager.update_heartbeat(session_id)

    user_id = redis_client.hget('user_mapping', f'session:{session_id}')
    if user_id:
        user_id = user_id.decode()
        timestamp = time()
        save_heartbeat_data(user_id, timestamp)


@socketio.on('connect')
def handle_connect():
    print(f'New connection attempt from SID: {request.sid}')


@socketio.on('register')
def handle_register(data):
    user_id = data['userId']
    session_id = request.sid
    user_manager.update_heartbeat(session_id)

    existing_session_id = redis_client.hget('user_mapping', f'user:{user_id}')
    if existing_session_id:
        # There's already a session for this user, refuse the new connection
        print(
            f"Rejecting new connection for user {user_id} because an existing session {existing_session_id.decode()} is active.")
        # Optionally send a message back to the client before disconnecting
        emit('error', {'message': 'Multiple connections are not allowed.'}, room=session_id)
        disconnect(session_id)
        return  # Stop further processing

    with redis_client.pipeline() as pipe:
        # Set the new session mapping as no existing session is found
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
