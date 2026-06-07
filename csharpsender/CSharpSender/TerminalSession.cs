using System;
using System.Threading.Tasks;

namespace CSharpSender
{
    /// <summary>
    /// Minimal terminal session shim. Rather than spawning an interactive shell, it simply
    /// reports that the feature is unavailable so the sender can compile/run in stripped builds.
    /// </summary>
    public sealed class TerminalSession : IDisposable
    {
        private readonly Func<string, Task> _onOutputAsync;
        private bool _isActive;

        public TerminalSession(Func<string, Task> onOutputAsync)
        {
            _onOutputAsync = onOutputAsync ?? throw new ArgumentNullException(nameof(onOutputAsync));
        }

        public void Start()
        {
            if (_isActive) return;
            _isActive = true;
            _ = _onOutputAsync("[TERMINAL] Interactive shell not available in this build.\n");
        }

        public void SendInput(string input)
        {
            if (!_isActive) return;
            _ = _onOutputAsync($"[TERMINAL] Ignored input: {input}\n");
        }

        public void Stop()
        {
            if (!_isActive) return;
            _isActive = false;
            _ = _onOutputAsync("[TERMINAL] Session closed.\n");
        }

        public void Dispose()
        {
            Stop();
        }
    }
}
