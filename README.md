# JoeRat - Remote Desktop Monitoring System

A comprehensive remote desktop monitoring solution with real-time screen sharing, remote control, and persistent deployment capabilities.

## 🚀 Features

### **Windows Agent (JoeRat.exe)**
- **Automatic Persistence**: Adds itself to Windows startup and AppData
- **Screen Streaming**: High-quality real-time screen capture (1920x1080 @ 30 FPS)
- **Remote Control**: Full mouse and keyboard input injection
- **System Telemetry**: CPU, GPU, memory monitoring
- **File Operations**: Upload/download files, directory browsing
- **Command Execution**: Remote command execution with output capture
- **WebSocket Communication**: Real-time streaming with auto-reconnection
- **Stealth Operation**: Runs hidden in background

### **Qt Viewer (Cross-Platform)**
- **Multi-Platform Support**: Windows, Linux, macOS compatibility
- **Live Desktop Viewing**: Real-time screen streaming
- **Remote Control Interface**: Send mouse/keyboard commands
- **File Manager**: Browse and transfer files remotely
- **Terminal Access**: Execute remote commands
- **Session Management**: Connect to multiple machines

### **WebSocket Server**
- **Node.js Backend**: Scalable WebSocket server
- **Room-Based Connections**: Secure isolated sessions
- **Authentication**: Secret-based access control
- **Message Routing**: Efficient real-time communication

## 📋 System Requirements

### **Windows Agent**
- Windows 10/11 (x64)
- No additional dependencies required (self-contained)
- User-level permissions (no admin needed)

### **Qt Viewer**
- Python 3.8+
- PyQt6
- Any modern operating system

### **Server**
- Node.js 16+
- npm or yarn

## 🛠️ Quick Start

### **1. Server Setup**
```bash
# Install dependencies
npm install

# Start server
node server.js
```

### **2. Windows Agent Deployment**
```bash
# Run the built executable
build/JoeRat.exe

# Agent will automatically:
# - Add itself to Windows startup
# - Copy to AppData as hidden file
# - Connect to WebSocket server
# - Begin streaming screen
```

### **3. Viewer Setup**
```bash
# Install Python dependencies
cd qt-viewer
pip install -r requirements.txt

# Launch viewer
python viewer.py
```

## 🎯 Usage Instructions

### **Basic Deployment**
1. Start the WebSocket server
2. Deploy `JoeRat.exe` on target Windows machine
3. Launch the Qt viewer on your machine
4. Connect using matching room ID and secret

### **Agent Features**
- **Persistence**: Automatic startup and AppData deployment
- **Screen Capture**: Continuous screen streaming
- **Remote Control**: Full input control
- **File Access**: Browse and transfer files
- **Command Shell**: Execute system commands
- **System Info**: Hardware and software monitoring

## 🔒 Security & Persistence

### **Agent Persistence**
- **Windows Startup**: Automatic registry entry
- **AppData Deployment**: Hidden in user AppData folder
- **Self-Healing**: Restarts if terminated
- **No Admin Required**: User-level installation
- **Stealth Mode**: Hidden operation

### **Connection Security**
- **Room Isolation**: Separate sessions per room
- **Secret Authentication**: Password-protected connections
- **WebSocket Encryption**: Secure communication channel
- **Timeout Protection**: Automatic session cleanup

## 📁 Project Structure

```
JoeRat/
├── server.js                 # WebSocket server
├── package.json              # Node.js dependencies
├── README.md                 # This documentation
├── qt-viewer/                # Qt viewer application
│   ├── viewer.py            # Main viewer application
│   ├── requirements.txt     # Python dependencies
│   └── logo.png             # Application icon
├── csharpsender/             # Windows agent source
│   └── CSharpSender/        # Agent source code
│       ├── Program.cs       # Entry point & persistence
│       ├── Form1.cs         # Main form & streaming
│       ├── StartupManager.cs # Windows persistence
│       └── InputHelper.cs   # Remote input handling
└── build/                    # Built executables
    └── JoeRat.exe           # Windows agent executable
```

## 🚀 Deployment Options

### **Windows Agent**
The executable is completely self-contained:
- **No Installation**: Portable executable
- **No Dependencies**: All libraries included
- **No Admin Rights**: User-level deployment
- **Automatic Setup**: Persistence on first run

## 📊 Performance Specifications

### **Streaming Quality**
- **Resolution**: 1920x1080 (configurable)
- **Frame Rate**: 30 FPS (adaptive)
- **Compression**: JPEG with quality adjustment
- **Bandwidth**: 1-3 Mbps per stream
- **Latency**: <100ms typical

### **Resource Usage**
- **CPU**: 5-15% during active streaming
- **Memory**: 50-100 MB per instance
- **Network**: Adaptive based on connection quality
- **Storage**: Minimal (logs only)

## 🛠️ Development

### **Building Windows Agent**
```bash
cd csharpsender/CSharpSender
dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true
```

## 🐛 Troubleshooting

### **Common Issues**
1. **Agent Not Starting**: Check Windows compatibility and .NET runtime
2. **Connection Failed**: Verify server status and firewall settings
3. **Screen Capture Issues**: Run as administrator if blocked by security
4. **File Transfer Problems**: Check folder permissions

### **Debug Information**
- **Agent Logs**: `sender-debug.log` in executable directory
- **Server Logs**: Console output and connection events
- **Viewer Logs**: Console output and error messages

### **Windows 11 Compatibility**
- Built with .NET 8 for Windows 11 compatibility
- Enhanced debugging for troubleshooting
- Automatic error reporting and logging

## ⚠️ Important Notes

### **Legal & Ethical Use**
This tool is intended for:
- **System Administration**: Remote IT support and management
- **Educational Purposes**: Learning about remote desktop technologies
- **Authorized Monitoring**: With proper consent and permissions

---

**JoeRat** - Professional Remote Desktop Monitoring Solution
