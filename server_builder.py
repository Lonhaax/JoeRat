#!/usr/bin/env python3

import os
import json
import subprocess
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
import uuid

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

class ServerBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.project_file = self.project_root / "csharpsender" / "CSharpSender" / "CSharpSender.csproj"
        self.build_dir = self.project_root / "build"
        self.builds = {}  # Track build status
        self.build_lock = threading.Lock()
        
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
            return True
        except Exception as e:
            print(f"Failed to update BuildConfig.cs: {e}")
            return False
    
    def build_executable(self, build_id, ws_url, room_id, secret, exe_name):
        """Build executable in background thread"""
        try:
            with self.build_lock:
                self.builds[build_id] = {
                    'status': 'building',
                    'progress': 0,
                    'message': 'Starting build...',
                    'start_time': time.time()
                }
            
            # Update configuration
            if not self.update_build_config(ws_url, room_id, secret, exe_name):
                with self.build_lock:
                    self.builds[build_id].update({
                        'status': 'failed',
                        'message': 'Failed to update BuildConfig.cs'
                    })
                return
            
            # Update progress
            with self.build_lock:
                self.builds[build_id].update({
                    'progress': 10,
                    'message': 'Configuration updated'
                })
            
            # Clean previous build
            if self.build_dir.exists():
                import shutil
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
            
            with self.build_lock:
                self.builds[build_id].update({
                    'progress': 30,
                    'message': 'Running dotnet publish...'
                })
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Rename to custom name if needed
                built_exe = self.build_dir / "CSharpSender.exe"
                target_exe = self.build_dir / f"{exe_name}.exe"
                
                if built_exe.exists() and exe_name != "CSharpSender":
                    built_exe.rename(target_exe)
                
                size_mb = target_exe.stat().st_size / (1024 * 1024)
                
                with self.build_lock:
                    self.builds[build_id].update({
                        'status': 'completed',
                        'progress': 100,
                        'message': f'Build successful: {exe_name}.exe ({size_mb:.1f} MB)',
                        'exe_path': str(target_exe),
                        'size_mb': round(size_mb, 1),
                        'end_time': time.time()
                    })
            else:
                with self.build_lock:
                    self.builds[build_id].update({
                        'status': 'failed',
                        'progress': 0,
                        'message': f'Build failed: {result.stderr}'
                    })
                    
        except subprocess.TimeoutExpired:
            with self.build_lock:
                self.builds[build_id].update({
                    'status': 'failed',
                    'message': 'Build timed out'
                })
        except Exception as e:
            with self.build_lock:
                self.builds[build_id].update({
                    'status': 'failed',
                    'message': f'Build error: {str(e)}'
                })

# Global builder instance
builder = ServerBuilder()

@app.route('/api/build', methods=['POST'])
def start_build():
    """Start a new build"""
    try:
        data = request.get_json()
        ws_url = data.get('ws_url', 'ws://localhost:8080')
        room_id = data.get('room_id', 'ops-room')
        secret = data.get('secret', 'boi123')
        exe_name = data.get('exe_name', 'CSharpSender')
        
        # Generate unique build ID
        build_id = str(uuid.uuid4())[:8]
        
        # Start build in background thread
        thread = threading.Thread(
            target=builder.build_executable,
            args=(build_id, ws_url, room_id, secret, exe_name)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'build_id': build_id,
            'message': 'Build started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/build/<build_id>/status', methods=['GET'])
def get_build_status(build_id):
    """Get build status"""
    try:
        with builder.build_lock:
            build_info = builder.builds.get(build_id)
            
        if build_info:
            return jsonify({
                'success': True,
                'build': build_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Build not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/build/<build_id>/download', methods=['GET'])
def download_build(build_id):
    """Download built executable"""
    try:
        with builder.build_lock:
            build_info = builder.builds.get(build_id)
            
        if not build_info or build_info['status'] != 'completed':
            return jsonify({
                'success': False,
                'error': 'Build not completed'
            }), 404
        
        exe_path = Path(build_info['exe_path'])
        if not exe_path.exists():
            return jsonify({
                'success': False,
                'error': 'Executable not found'
            }), 404
        
        # Return file info (actual download would need file serving setup)
        return jsonify({
            'success': True,
            'file_info': {
                'name': exe_path.name,
                'size': exe_path.stat().st_size,
                'path': str(exe_path)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/builds', methods=['GET'])
def list_builds():
    """List all builds"""
    try:
        with builder.build_lock:
            builds = {
                build_id: {
                    'status': info['status'],
                    'progress': info['progress'],
                    'message': info['message'],
                    'start_time': info.get('start_time'),
                    'end_time': info.get('end_time')
                }
                for build_id, info in builder.builds.items()
            }
        
        return jsonify({
            'success': True,
            'builds': builds
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def server_status():
    """Get server status"""
    try:
        # Check if dotnet is available
        try:
            result = subprocess.run(['dotnet', '--version'], capture_output=True, text=True, timeout=5)
            dotnet_version = result.stdout.strip() if result.returncode == 0 else 'Not available'
        except:
            dotnet_version = 'Not available'
        
        # Check project file
        project_exists = builder.project_file.exists()
        
        return jsonify({
            'success': True,
            'status': {
                'server': 'running',
                'dotnet_version': dotnet_version,
                'project_exists': project_exists,
                'project_path': str(builder.project_file),
                'active_builds': len([b for b in builder.builds.values() if b['status'] == 'building'])
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("🚀 Starting Server Build System...")
    print(f"📁 Project: {builder.project_file}")
    print(f"🔧 Build Directory: {builder.build_dir}")
    print("🌐 Server will be available at: http://localhost:5000")
    print()
    print("API Endpoints:")
    print("  POST /api/build - Start new build")
    print("  GET  /api/build/<id>/status - Get build status")
    print("  GET  /api/build/<id>/download - Download executable")
    print("  GET  /api/builds - List all builds")
    print("  GET  /api/status - Server status")
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=False)
