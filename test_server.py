#!/usr/bin/env python3

import requests
import json
import time

def test_server():
    """Test the server build system"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Server Build System")
    print("=" * 40)
    
    # Test 1: Check server status
    print("1. Testing server status...")
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Server is running: {status.get('status', {}).get('server')}")
            print(f"   .NET Version: {status.get('status', {}).get('dotnet_version')}")
            print(f"   Project exists: {status.get('status', {}).get('project_exists')}")
        else:
            print(f"❌ Server status failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("💡 Make sure server_builder.py is running")
        return False
    
    print()
    
    # Test 2: Start a build
    print("2. Starting test build...")
    build_data = {
        "ws_url": "ws://vnc.jake.cash:3000",
        "room_id": "ops-room", 
        "secret": "boi123",
        "exe_name": "testserver"
    }
    
    try:
        response = requests.post(f"{base_url}/api/build", json=build_data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                build_id = result.get('build_id')
                print(f"✅ Build started: ID {build_id}")
                
                # Test 3: Poll build status
                print("\n3. Monitoring build progress...")
                max_attempts = 12  # 2 minutes max
                
                for attempt in range(max_attempts):
                    try:
                        status_response = requests.get(f"{base_url}/api/build/{build_id}/status", timeout=5)
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            if status_data.get('success'):
                                build_info = status_data.get('build')
                                status = build_info.get('status')
                                progress = build_info.get('progress', 0)
                                message = build_info.get('message', '')
                                
                                print(f"   [{progress}%] {message}")
                                
                                if status == 'completed':
                                    print(f"\n✅ Build completed successfully!")
                                    print(f"   Executable: {build_info.get('exe_path')}")
                                    print(f"   Size: {build_info.get('size_mb', 'N/A')} MB")
                                    return True
                                elif status == 'failed':
                                    print(f"\n❌ Build failed: {message}")
                                    return False
                                
                                time.sleep(10)  # Wait before next check
                            else:
                                print(f"   ❌ Status check failed: {status_data.get('error')}")
                                break
                        else:
                            print(f"   ⚠️ Status check error: HTTP {status_response.status_code}")
                            break
                    except Exception as e:
                        print(f"   ⚠️ Status check error: {e}")
                        time.sleep(5)
                        continue
                
                print(f"\n⏰ Build monitoring timeout")
                return False
            else:
                print(f"❌ Failed to start build: {result.get('error')}")
                return False
        else:
            print(f"❌ Build request failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Build request error: {e}")
        return False

if __name__ == "__main__":
    print("📋 Make sure server_builder.py is running on localhost:5000")
    print("   Run: python server_builder.py")
    print()
    
    success = test_server()
    
    if success:
        print("\n🎉 Server build system test passed!")
    else:
        print("\n❌ Server build system test failed!")
        print("\n🔧 Troubleshooting:")
        print("   1. Start server: python server_builder.py")
        print("   2. Check .NET SDK is installed")
        print("   3. Verify project file exists")
        print("   4. Check firewall settings")
