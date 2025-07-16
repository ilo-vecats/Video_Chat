from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, join_room

# Use a more specific path for static files to avoid conflicts
app = Flask(__name__, static_folder='static', static_url_path='/static')
socketio = SocketIO(app, cors_allowed_origins='*')

# A dictionary to hold rooms and their members (sids)
rooms = {}

@app.route('/')
def index():
    """Serve the main HTML file."""
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve other static files like main.js."""
    return send_from_directory('static', filename)

@socketio.on('connect')
def handle_connect():
    """Log when a new client connects."""
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f"Client disconnected: {request.sid}")
    # Find which room the user was in and remove them
    for room_id, members in list(rooms.items()):
        if request.sid in members:
            members.remove(request.sid)
            # Notify the other member that the peer has left
            for member_sid in members:
                emit('peer_left', {'sid': request.sid}, room=member_sid)
            # If the room is now empty, delete it
            if not members:
                del rooms[room_id]
            print(f"Client {request.sid} removed from room {room_id}")
            break

@socketio.on('join')
def handle_join(data):
    """Handle a user joining a room."""
    room_id = data['room']
    sid = request.sid
    join_room(room_id)

    if room_id not in rooms:
        rooms[room_id] = []
    
    # Get other members in the room before adding the new one
    other_members = rooms[room_id]
    
    # Add the new member to the room
    rooms[room_id].append(sid)

    print(f"Client {sid} joined room {room_id}")
    print(f"Room {room_id} members: {rooms[room_id]}")

    # If there are other members, the new user will initiate the connection.
    # This logic is for a simple 2-person room.
    if other_members:
        # The new user (sid) will be the "offerer"
        # The existing user (other_members[0]) will be the "answerer"
        
        # Tell the new user to create an offer for the existing user
        emit('initiate_peer_connection', {'peer_sid': other_members[0], 'create_offer': True}, room=sid)
        
        # Tell the existing user to prepare for a connection from the new user
        emit('initiate_peer_connection', {'peer_sid': sid, 'create_offer': False}, room=other_members[0])
    else:
        # This is the first user in the room, so they just wait.
        print(f"User {sid} is the first in room {room_id}, waiting for a peer.")

@socketio.on('signal')
def handle_signal(data):
    """Forward the WebRTC signal (offer, answer, or ICE candidate) to the target peer."""
    target_sid = data['target_sid']
    signal = data['signal']
    
    # It's crucial that the signal includes who it came from.
    emit('signal', {'sender_sid': request.sid, 'signal': signal}, room=target_sid)

if __name__ == '__main__':
    print("Server starting on http://localhost:5050")
    # Set debug=False for production
    socketio.run(app, host='0.0.0.0', port=5050, debug=True)
