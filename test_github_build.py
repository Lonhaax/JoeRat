#!/usr/bin/env python3

import urllib.request
import json

# Test repository access
repo = 'Lonhaax/JoeRat'
pat = 'YOUR_GITHUB_TOKEN_HERE'

print("🔍 Testing GitHub repository access...")

try:
    # Test repo access
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}')
    req.add_header('Authorization', f'Bearer {pat}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            print(f'✅ Repository accessible: {data["full_name"]}')
            print(f'   Private: {data["private"]}')
            print(f'   Default branch: {data["default_branch"]}')
        else:
            print(f'❌ Repository access failed: HTTP {resp.status}')
            
    # Test workflow access
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/workflows')
    req.add_header('Authorization', f'Bearer {pat}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            workflows = json.loads(resp.read().decode())
            print(f'✅ Workflows accessible: {len(workflows["workflows"])} found')
            for wf in workflows['workflows']:
                if wf['name'] == 'build-sender':
                    print(f'   ✅ Found build-sender.yml workflow')
                    break
            else:
                print(f'   ❌ build-sender.yml workflow not found')
        else:
            print(f'❌ Workflow access failed: HTTP {resp.status}')
            
except Exception as e:
    print(f'❌ Error: {e}')

print("\n🎯 GitHub build system is ready!")
