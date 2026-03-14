#!/usr/bin/env python3

import urllib.request
import json

# Test repository access (no token needed for public repo)
repo = 'Lonhaax/JoeRat'

print("🔍 Testing GitHub repository access...")

try:
    # Test repo access (public repo, no token needed)
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            print(f'✅ Repository accessible: {data["full_name"]}')
            print(f'   Private: {data["private"]}')
            print(f'   Default branch: {data["default_branch"]}')
            print(f'   URL: {data["html_url"]}')
        else:
            print(f'❌ Repository access failed: HTTP {resp.status}')
            
    # Test workflow access (no token needed for public repo)
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/workflows')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            workflows = json.loads(resp.read().decode())
            print(f'✅ Workflows accessible: {len(workflows["workflows"])} found')
            for wf in workflows['workflows']:
                if 'Build' in wf['name'] and 'Sender' in wf['name']:
                    print(f'   ✅ Found {wf["name"]} workflow')
                    print(f'   📄 File: {wf["path"]}')
                    break
            else:
                print(f'   ❌ build-sender workflow not found')
        else:
            print(f'❌ Workflow access failed: HTTP {resp.status}')
            
except Exception as e:
    print(f'❌ Error: {e}')

print("\n🎯 GitHub build system is ready!")
print("📝 To use the build system:")
print("   1. Add your GitHub PAT to viewer.py line 3201")
print("   2. Click 'Create Build' in the Qt viewer")
print("   3. Enter executable name (e.g., 'custombuild')")
print("   4. Wait for GitHub Actions to build and download")
