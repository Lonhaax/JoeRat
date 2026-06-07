import asyncio
import websockets

async def test_connection():
    try:
        print("Testing WebSocket connection to ws://vnc.jake.cash:3000...")
        async with websockets.connect("ws://vnc.jake.cash:3000") as websocket:
            print("✅ Connected successfully!")
            
            # Test sending a message
            await websocket.send('{"type":"ping"}')
            print("✅ Message sent!")
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print(f"✅ Response received: {response}")
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
