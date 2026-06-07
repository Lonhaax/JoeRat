import asyncio
import websockets
import json

async def test_full_join():
    try:
        print("Testing full join process...")
        async with websockets.connect("ws://vnc.jake.cash:3000") as websocket:
            print("✅ Connected successfully!")
            
            # Send join message like the sender does
            machine_id = "TestSender"
            join_message = {
                "type": "join",
                "role": "sender", 
                "roomId": "ops-room",
                "secret": "boi123",
                "machineId": machine_id
            }
            
            await websocket.send(json.dumps(join_message))
            print("✅ Join message sent!")
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print(f"✅ Response received: {response}")
            
            # Parse response
            try:
                resp_data = json.loads(response)
                if resp_data.get("type") == "join-success":
                    print("🎉 Successfully joined room!")
                else:
                    print(f"❌ Join failed: {resp_data}")
            except:
                print(f"❌ Could not parse response: {response}")
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_full_join())
