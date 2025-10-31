from gevent import monkey; monkey.patch_all()
from flask import Flask, send_from_directory, request
import os
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session

# Use a more specific path for static files to avoid conflicts
app = Flask(__name__, static_folder='static', static_url_path='/static')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='gevent')

# A dictionary to hold rooms and their members (sids)
rooms = {}

# Map socket sid -> room_id for quick lookup
sid_to_room = {}

# Persist simple collaborative state per room so late joiners get current data
# Structure: { room_id: { 'notes': str, 'language': str, 'codes': { 'python': str, 'java': str, 'cpp': str, 'javascript': str } } }
room_state = {}

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///video_chat.db')
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autocommit=False, autoflush=False))
Base = declarative_base()


class Meeting(Base):
    __tablename__ = 'meetings'
    id = Column(Integer, primary_key=True)
    room_id = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    participants = relationship('Participant', back_populates='meeting', cascade='all, delete-orphan')
    notes = relationship('Note', back_populates='meeting', cascade='all, delete-orphan')


class Participant(Base):
    __tablename__ = 'participants'
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'), nullable=False)
    sid = Column(String(255), index=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    left_at = Column(DateTime)
    meeting = relationship('Meeting', back_populates='participants')


class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'), nullable=False)
    content = Column(Text, default='')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meeting = relationship('Meeting', back_populates='notes')


Base.metadata.create_all(bind=engine)

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
    room_id = sid_to_room.pop(request.sid, None)
    if room_id is not None and room_id in rooms:
        members = rooms[room_id]
        if request.sid in members:
            members.remove(request.sid)
        # Notify remaining members that this peer left
        for member_sid in members:
            emit('peer_left', {'sid': request.sid}, room=member_sid)
        # If the room is now empty, clean up
        if not members:
            final_notes = room_state.get(room_id, {}).get('notes', '')
            # Notify last known socket (no members left) is not possible, so only cleanup
            del rooms[room_id]
            room_state.pop(room_id, None)
        # mark participant left
        db = SessionLocal()
        try:
            participant = db.query(Participant).filter_by(sid=request.sid).one_or_none()
            if participant and not participant.left_at:
                participant.left_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        print(f"Client {request.sid} removed from room {room_id}")

@socketio.on('join')
def handle_join(data):
    """Handle a user joining a room."""
    room_id = data['room']
    sid = request.sid
    join_room(room_id)

    if room_id not in rooms:
        rooms[room_id] = []
    if room_id not in room_state:
        # default room state
        room_state[room_id] = {
            'notes': '',
            'language': 'python',
            'codes': {
                'python': '',
                'java': '',
                'cpp': '',
                'javascript': ''
            }
        }
    
    # Get other members in the room before adding the new one
    other_members = rooms[room_id]
    
    # Add the new member to the room
    rooms[room_id].append(sid)
    sid_to_room[sid] = room_id

    print(f"Client {sid} joined room {room_id}")
    print(f"Room {room_id} members: {rooms[room_id]}")

    # Persist meeting/participant and send current room state to the newly joined user
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter_by(room_id=room_id).one_or_none()
        if not meeting:
            meeting = Meeting(room_id=room_id)
            db.add(meeting)
            db.flush()
        # ensure one note row exists per meeting
        note = db.query(Note).filter_by(meeting_id=meeting.id).one_or_none()
        if not note:
            note = Note(meeting_id=meeting.id, content='')
            db.add(note)
        # add participant
        participant = Participant(meeting_id=meeting.id, sid=sid)
        db.add(participant)
        db.commit()
    finally:
        db.close()

    # Send current room state to the newly joined user
    emit('room_state', room_state[room_id], room=sid)

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


@socketio.on('notes_update')
def handle_notes_update(data):
    """Handle shared notes text updates and broadcast to room (except sender)."""
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id:
        return
    text = data.get('text', '')
    # update room state
    if room_id in room_state:
        room_state[room_id]['notes'] = text
    # persist note
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter_by(room_id=room_id).one_or_none()
        if meeting:
            note = db.query(Note).filter_by(meeting_id=meeting.id).one_or_none()
            if note:
                note.content = text
            else:
                note = Note(meeting_id=meeting.id, content=text)
                db.add(note)
            db.commit()
    finally:
        db.close()
    emit('notes_update', {'text': text}, room=room_id, include_self=False)


@socketio.on('end_meeting')
def handle_end_meeting():
    """End meeting: broadcast final notes to all participants in the room."""
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id:
        return
    notes = room_state.get(room_id, {}).get('notes', '')
    emit('meeting_ended', {'notes': notes}, room=room_id)


@socketio.on('code_update')
def handle_code_update(data):
    """Handle code editor content updates and broadcast to room (except sender)."""
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id:
        return
    code = data.get('code', '')
    language = data.get('language', room_state.get(room_id, {}).get('language', 'python'))
    if room_id in room_state:
        room_state[room_id]['codes'][language] = code
    emit('code_update', {'code': code, 'language': language}, room=room_id, include_self=False)


@socketio.on('language_update')
def handle_language_update(data):
    """Handle language selection changes and broadcast to room (except sender)."""
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id:
        return
    language = data.get('language', 'python')
    if room_id in room_state:
        room_state[room_id]['language'] = language
    emit('language_update', {'language': language}, room=room_id, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    print(f"Server starting on http://0.0.0.0:{port}")
    # Set debug=False for production
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
