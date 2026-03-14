#!/usr/bin/env python3

import urllib.request
import json

def test_token_permissions():
    """Test what permissions the GitHub token has"""
    pat = "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"
    repo = "Lonhaax/JoeRat"
    
    print("🔍 Testing GitHub Token Permissions")
    print("=" * 40)
    
    # Test 1: Basic user access
    print("1. Testing basic user access...")
    try:
        req = urllib.request.Request("https://api.github.com/user")
        req.add_header('Authorization', f'Bearer {pat}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                user = json.loads(resp.read().decode())
                print(f"✅ User access: {user['login']}")
            else:
                print(f"❌ User access failed: HTTP {resp.status}")
    except Exception as e:
        print(f"❌ User access error: {e}")
    
    # Test 2: Repository access
    print("\n2. Testing repository access...")
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}")
        req.add_header('Authorization', f'Bearer {pat}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                repo_data = json.loads(resp.read().decode())
                print(f"✅ Repo access: {repo_data['full_name']}")
                print(f"   Permissions: {repo_data.get('permissions', {})}")
            else:
                print(f"❌ Repo access failed: HTTP {resp.status}")
    except Exception as e:
        print(f"❌ Repo access error: {e}")
    
    # Test 3: Branch access (this is what's failing)
    print("\n3. Testing branch access...")
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/git/refs/heads/master")
        req.add_header('Authorization', f'Bearer {pat}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("✅ Branch access: OK")
            else:
                print(f"❌ Branch access failed: HTTP {resp.status}")
    except Exception as e:
        print(f"❌ Branch access error: {e}")
    
    # Test 4: Workflow access
    print("\n4. Testing workflow access...")
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows")
        req.add_header('Authorization', f'Bearer {pat}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("✅ Workflow access: OK")
            else:
                print(f"❌ Workflow access failed: HTTP {resp.status}")
    except Exception as e:
        print(f"❌ Workflow access error: {e}")
    
    print("\n🔧 Required Token Scopes:")
    print("   ✅ repo - Full repository access")
    print("   ✅ workflow - Workflow access")
    print("\n📝 To fix this:")
    print("   1. Go to https://github.com/settings/tokens")
    print("   2. Click 'Generate new token (classic)'")
    print("   3. Select scopes:")
    print("      ☑️ repo (Full control of private repositories)")
    print("      ☑️ workflow (Update GitHub Action workflows)")
    print("   4. Generate token and copy it")
    print("   5. Replace token in viewer.py line 3201")

if __name__ == "__main__":
    test_token_permissions()
