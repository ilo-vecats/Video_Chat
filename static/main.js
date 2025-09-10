const socket = io(); // Auto-connects to the same server serving this file
let localStream;
const peerConnections = new Map();

const config = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
};

const localVideo = document.getElementById('localVideo');
localVideo.classList.add('videoTile');
const joinBtn = document.getElementById('joinBtn');
const roomInput = document.getElementById('roomInput');
const videosContainer = document.getElementById('videosContainer');
const sharedNotes = document.getElementById('sharedNotes');
const toggleNotesBtn = document.getElementById('toggleNotesBtn');
const endMeetingBtn = document.getElementById('endMeetingBtn');

let currentLanguage = 'python';
let inRoom = false;

// Join a room
joinBtn.onclick = async () => {
  const roomName = roomInput.value.trim();
  if (!roomName) {
    alert('Please enter a room name.');
    return;
  }

  try {
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = localStream;
    socket.emit('join', { room: roomName });
    // Disable inputs until room_state arrives to prevent lost updates
    if (sharedNotes) sharedNotes.disabled = true;
  } catch (error) {
    console.warn('Camera/mic not available or denied. Video will be disabled.');
    // still join room without media
    socket.emit('join', { room: roomName });
    if (sharedNotes) sharedNotes.disabled = true;
  }
};

// Toggle Notes Mode layout
toggleNotesBtn?.addEventListener('click', () => {
  document.body.classList.toggle('notes-mode');
});

endMeetingBtn?.addEventListener('click', () => {
  if (!inRoom) return;
  socket.emit('end_meeting');
});

// Shared notes input
sharedNotes?.addEventListener('input', (e) => {
  if (inRoom) socket.emit('notes_update', { text: e.target.value });
});

// Server tells us to connect to a peer
socket.on('initiate_peer_connection', async ({ peer_sid, create_offer }) => {
  const pc = createPeerConnection(peer_sid);
  peerConnections.set(peer_sid, pc);

  localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

  if (create_offer) {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.emit('signal', { target_sid: peer_sid, signal: { sdp: pc.localDescription } });
  }
});

// Receive signals (SDP or ICE)
socket.on('signal', async ({ sender_sid, signal }) => {
  const pc = peerConnections.get(sender_sid);
  if (!pc) return;

  if (signal.sdp) {
    await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));
    if (signal.sdp.type === 'offer') {
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      socket.emit('signal', { target_sid: sender_sid, signal: { sdp: pc.localDescription } });
    }
  } else if (signal.candidate) {
    await pc.addIceCandidate(new RTCIceCandidate(signal.candidate));
  }
});

// Sync events from server for collaboration
socket.on('room_state', ({ notes }) => {
  inRoom = true;
  if (typeof notes === 'string' && sharedNotes) {
    sharedNotes.value = notes;
    sharedNotes.disabled = false;
  }
});

socket.on('notes_update', ({ text }) => {
  if (sharedNotes && document.activeElement !== sharedNotes) {
    sharedNotes.value = text;
  }
});

// Remove code editor sync listeners

// Handle disconnection
socket.on('peer_left', ({ sid }) => {
  const video = document.getElementById(`remoteVideo-${sid}`);
  if (video) {
    video.remove();
  }
  if (peerConnections.has(sid)) {
    peerConnections.get(sid).close();
    peerConnections.delete(sid);
  }
});

// Show final notes when meeting ends
socket.on('meeting_ended', ({ notes }) => {
  if (sharedNotes) {
    sharedNotes.value = notes || '';
  }
  // Force notes mode to focus on notes
  document.body.classList.add('notes-mode', 'meeting-ended');
  // Stop local media
  if (localStream) {
    try {
      localStream.getTracks().forEach(t => t.stop());
    } catch (e) {
      console.warn('Error stopping local tracks', e);
    }
    localStream = null;
  }
  if (localVideo) {
    try { localVideo.srcObject = null; } catch {}
  }
  // Close all peer connections
  peerConnections.forEach(pc => {
    try { pc.close(); } catch {}
  });
  peerConnections.clear();
  // Remove all remote video elements
  const remotes = document.querySelectorAll('[id^="remoteVideo-"]');
  remotes.forEach(v => v.remove());
  // Optionally hide local video
  if (localVideo) {
    localVideo.style.display = 'none';
  }
  alert('Meeting ended. Final notes are displayed.');
});

// Create a new peer connection
function createPeerConnection(peer_sid) {
  const pc = new RTCPeerConnection(config);

  pc.onicecandidate = event => {
    if (event.candidate) {
      socket.emit('signal', { target_sid: peer_sid, signal: { candidate: event.candidate } });
    }
  };

  pc.ontrack = event => {
    const remoteStream = event.streams[0];
    let video = document.getElementById(`remoteVideo-${peer_sid}`);

    if (!video) {
      video = document.createElement('video');
      video.id = `remoteVideo-${peer_sid}`;
      video.autoplay = true;
      video.playsInline = true;
      video.classList.add('videoTile');
      videosContainer.appendChild(video);
    }

    video.srcObject = remoteStream;
  };

  return pc;
}

// Cleanup on unload
window.onbeforeunload = () => {
  if (localStream) {
    localStream.getTracks().forEach(track => track.stop());
  }
  peerConnections.forEach(pc => pc.close());
  socket.disconnect();
};
