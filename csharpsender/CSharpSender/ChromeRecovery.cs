using System.Text.Json;
using System.Threading.Tasks;

namespace CSharpSender
{
    /// <summary>
    /// Minimal Chrome recovery helper so the sender can compile even when the full recovery
    /// tooling is not bundled with the build artifacts. Returns a deterministic "unsupported"
    /// response.
    /// </summary>
    public static class ChromeRecovery
    {
        public static Task<string> HandleChromeRecoveryCommand(string action, string machineId)
        {
            var response = new
            {
                type = "command-output",
                requestId = "chrome-recovery",
                machineId,
                status = "unsupported",
                action,
                message = "Chrome recovery tooling not included in this build"
            };

            return Task.FromResult(JsonSerializer.Serialize(response));
        }
    }
}
