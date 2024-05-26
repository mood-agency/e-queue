import threading
import time

import requests  # Import the requests library
import socketio

sio = socketio.Client()


def send_heartbeat(sio, user_id):
    while True:
        print(f'User {user_id} sending heartbeat at {time.strftime("%X")}')
        sio.emit('heartbeat')
        time.sleep(10)  # Heartbeat every 10 seconds


def check_session_active(user_id):
    while True:
        try:
            response = requests.get(f'http://localhost:5000/api/user_session_active/{user_id}')
            data = response.json()
            if not data['active']:
                print(f'User {user_id} session {data["session_id"]} is inactive.')
            else:
                print(f'User {user_id} session {data["session_id"]} is active.')
        except Exception as e:
            raise f'Error checking session status for user {user_id}: {str(e)}'
        time.sleep(10)  # Check every 10 seconds


def user_connection(user_id):
    sio = socketio.Client()

    @sio.event
    def connect():
        print(f"User {user_id} connected to the server")
        sio.emit('register', {'userId': f'{user_id}'})
        threading.Thread(target=send_heartbeat, args=(sio, user_id), daemon=True).start()
        threading.Thread(target=check_session_active, args=(user_id,), daemon=True).start()

    @sio.event
    def disconnect():
        print(f"User {user_id} disconnected from the server")

    try:
        sio.connect('http://localhost:5000')  # Update with your actual server URL
    except socketio.exceptions.ConnectionError as e:
        print(f"User {user_id} connection failed: {str(e)}")

    return sio


def main():
    users = []
    for user_id in range(1, 100):
        sio = user_connection(user_id)
        users.append(sio)

    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Main program interrupted. Exiting...")
        for sio in users:
            sio.disconnect()


if __name__ == '__main__':
    main()
