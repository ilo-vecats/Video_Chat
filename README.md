#   Video_Chat
# Live on render -> https://video-chat-iro9.onrender.com/
# 📹 WebRTC Video Chat App

A lightweight, FaceTime-style video chat app built using **WebRTC**, **Flask**, and **Socket.IO** — enabling real-time peer-to-peer video calls directly from the browser.

---

## 🌟 Features

- 📡 Peer-to-peer connection via WebRTC
- 🔁 Real-time signaling using Flask + Socket.IO
- 🔒 Secure camera/mic permission handling
- 🔐 Supports HTTPS via ngrok for secure external testing

---

## 🧱 Tech Stack

| Layer       | Tech Used                        |
|-------------|----------------------------------|
| Frontend    | HTML, CSS, Vanilla JS            |
| Backend     | Python Flask, Flask-SocketIO     |
| Real-Time   | WebRTC, Socket.IO                |
| Tunneling   | ngrok (for HTTPS & cross-device) |

---
### **🐍  Create & Activate a Virtual Environment**

```
python3 -m venv venv
source venv/bin/activate       # macOS/Linux
# OR
venv\Scripts\activate          # Windows
```

---

### **📦  Install Required Python Packages**

```
pip install flask flask-socketio eventlet
```

---

### **▶️  Run the Server**

```
python server.py
```

By default, the app runs at:http://localhost:5050
## **🌐 Optional: Use HTTPS & Connect Across Devices with Ngrok**

Want to run this between your laptop and phone over Wi-Fi?

### **✅ Install ngrok**

```
brew install ngrok               # macOS (via Homebrew)
# OR
choco install ngrok              # Windows (via Chocolatey)
# OR
Download from https://ngrok.com/download
```

### **🚀 Start an HTTPS Tunnel to Your Flask Server**

```
ngrok http 5050
```

It will give you a URL like:

```
https://abc123.ngrok.io
```

Open this link on **both your devices (e.g. laptop + phone)** and join the same room.
