# Automatic Windows Startup & AppData Deployment

This application automatically adds itself to Windows startup and moves to AppData for persistence. No user input or command-line arguments are required.

## How It Works

When the application starts, it automatically:

1. **Checks** if it's already in Windows startup
2. **Adds itself** to startup if not already present
3. **Checks** if it's running from AppData
4. **Moves itself** to AppData as hidden file if not already there
5. **Updates** startup registry to point to AppData location
6. **Continues** running normally

## Deployment Locations

### Initial Run (from any location):
- Application runs from current location
- Automatically copies to: `%AppData%\[AppName]\[AppName].exe`
- Sets file as hidden
- Updates Windows startup registry

### Subsequent Runs:
- Application runs from AppData location
- Already hidden and persistent
- Startup registry points to AppData location

## File Locations

- **AppData Folder**: `%AppData%\[AppName]\` (e.g., `C:\Users\[User]\AppData\Roaming\CSharpSender\`)
- **Hidden Executable**: `%AppData%\[AppName]\[AppName].exe` (hidden attribute)
- **Registry Entry**: `HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\[AppName]`

## Dynamic Name Detection

The system automatically detects the actual program name from the executable file, so:

- If your executable is `MyRemoteApp.exe`, it moves to `%AppData%\MyRemoteApp\MyRemoteApp.exe`
- If your executable is `MonitorTool.exe`, it moves to `%AppData%\MonitorTool\MonitorTool.exe`
- The system adapts to whatever you name the executable

## User Experience

- **First Run**: 
  - Application adds itself to startup
  - Copies itself to AppData as hidden file
  - Updates registry to point to AppData location
  - Shows message to close and run from AppData
- **Subsequent Runs**: 
  - Application runs from AppData (already hidden)
  - Checks startup status and runs normally
- **No Messages**: No popup windows or user prompts after first run
- **No Commands**: No command-line arguments needed

## Security & Persistence Features

- **Hidden File**: Executable is marked as hidden in AppData
- **User-Level Only**: Uses HKEY_CURRENT_USER (no admin required)
- **AppData Storage**: Standard Windows application data location
- **Automatic Updates**: Startup registry always points to current AppData location
- **No Trace**: Original file can be deleted after AppData deployment

## Requirements

- Windows operating system
- Application must be run at least once to establish AppData location
- No administrator privileges required
- Write access to user's AppData folder

## Troubleshooting

If automatic deployment doesn't work:

1. Check the debug log file `sender-debug.log` in the application directory
2. Verify the registry entry exists in `regedit` under the path mentioned above
3. Check AppData folder: `%AppData%\[AppName]\`
4. Make sure the application has write permissions to AppData
5. Ensure the executable path is accessible

## Manual Removal

To completely remove the application:

1. **Remove from Startup**:
   - Open **Task Manager** (Ctrl+Shift+Esc)
   - Go to the **Startup** tab
   - Find your application and **Disable**

2. **Remove Registry Entry**:
   - Press **Win+R**, type `regedit`, press Enter
   - Navigate to `HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`
   - Delete the entry with your application's name

3. **Remove AppData Files**:
   - Navigate to `%AppData%\[AppName]\`
   - Delete the entire folder (may need to show hidden files)

## Security Note

The application stores itself in the current user's AppData folder only, not system-wide locations. This means:
- It only runs when the specific user account logs in
- No administrator privileges are required
- Other users on the same machine are not affected
- Files are stored in standard Windows application data location
