const socket = io(); // Auto-connects to the same server serving this file
let localStream;
const peerConnections = new Map();

const config = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
};

const localVideo = document.getElementById('localVideo');
const joinBtn = document.getElementById('joinBtn');
const roomInput = document.getElementById('roomInput');
const videosContainer = document.getElementById('videosContainer');

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
  } catch (error) {
    alert('Camera/mic access denied or blocked by HTTP.');
    console.error(error);
  }
};

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
      video.style.width = '45%';
      video.style.margin = '10px';
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