import os
from flask import Flask, session, redirect, url_for, request, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
import msal
from dotenv import load_dotenv
from datetime import datetime
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")

CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["User.Read"]

# File upload configuration
UPLOAD_FOLDER = 'uploads'
METADATA_FOLDER = 'metadata'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
# Create folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(METADATA_FOLDER, exist_ok=True)

# Role definitions
ADMIN_ROLE = "Game.Lead.Admin"
VIEWER_ROLE = "Game.Tester.Player"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )

def get_user_roles(user_data):
    """Extract roles from user session data"""
    return user_data.get('roles', [])

def is_admin(user_data):
    """Check if user has admin role"""
    roles = get_user_roles(user_data)
    return ADMIN_ROLE in roles

def is_viewer(user_data):
    """Check if user has viewer role"""
    roles = get_user_roles(user_data)
    return VIEWER_ROLE in roles or ADMIN_ROLE in roles

def get_file_metadata(filename):
    """Get metadata for a file"""
    metadata_path = os.path.join(METADATA_FOLDER, f"{filename}.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            return json.load(f)
    return None

def save_file_metadata(filename, user_email, original_filename):
    """Save metadata for a file"""
    metadata = {
        'filename': filename,
        'original_filename': original_filename,
        'user_email': user_email,
        'upload_date': datetime.now().isoformat(),
        'size': os.path.getsize(os.path.join(UPLOAD_FOLDER, filename))
    }
    metadata_path = os.path.join(METADATA_FOLDER, f"{filename}.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f)
    return metadata

def get_all_files():
    """Get all files (for admins to see everything)"""
    all_files = []
    if not os.path.exists(METADATA_FOLDER):
        return all_files
    
    for metadata_file in os.listdir(METADATA_FOLDER):
        if metadata_file.endswith('.json'):
            try:
                with open(os.path.join(METADATA_FOLDER, metadata_file), 'r') as f:
                    metadata = json.load(f)
                    all_files.append(metadata)
            except:
                continue
    # Sort by upload date, newest first
    all_files.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
    return all_files

def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def format_date(iso_date):
    """Format ISO date to readable format"""
    try:
        dt = datetime.fromisoformat(iso_date)
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except:
        return iso_date

def is_image(filename):
    """Check if file is an image"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in {'png', 'jpg', 'jpeg'}

def is_pdf(filename):
    """Check if file is a PDF"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext == 'pdf'

@app.route("/")
def home():
    user = session.get("user")
    if user:
        user_email = user.get('preferred_username')
        user_is_admin = is_admin(user)
        
        # Admins see all files, Viewers see all files (but can't modify)
        files = get_all_files()
        
        # Determine user role display
        if user_is_admin:
            role_display = "👑 Administrator"
            role_color = "#28a745"
        else:
            role_display = "👁️ Viewer"
            role_color = "#0078d4"
        
        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>SecureCloud Vault</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        max-width: 1200px;
                        margin: 50px auto;
                        padding: 20px;
                        background-color: #f5f5f5;
                    }
                    .container {
                        background: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    h2 {
                        color: #333;
                        margin-top: 0;
                    }
                    .user-info {
                        background: #e8f4f8;
                        padding: 15px;
                        border-radius: 5px;
                        margin-bottom: 20px;
                    }
                    .role-badge {
                        display: inline-block;
                        background: {{ role_color }};
                        color: white;
                        padding: 5px 15px;
                        border-radius: 20px;
                        font-size: 14px;
                        font-weight: bold;
                        margin-top: 5px;
                    }
                    .upload-section {
                        margin: 30px 0;
                        padding: 20px;
                        border: 2px dashed #0078d4;
                        border-radius: 5px;
                        background: #f9f9f9;
                    }
                    .admin-only {
                        {% if not user_is_admin %}
                        display: none !important;
                        {% endif %}
                    }
                    .file-list {
                        margin-top: 20px;
                    }
                    .file-item {
                        padding: 15px;
                        background: #f8f8f8;
                        margin: 10px 0;
                        border-radius: 5px;
                        border: 1px solid #e0e0e0;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    .file-info {
                        flex-grow: 1;
                    }
                    .file-name {
                        font-weight: bold;
                        color: #333;
                        margin-bottom: 5px;
                    }
                    .file-meta {
                        font-size: 12px;
                        color: #666;
                    }
                    .file-actions {
                        display: flex;
                        gap: 10px;
                    }
                    button, input[type="submit"], .btn {
                        background: #0078d4;
                        color: white;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 14px;
                        text-decoration: none;
                        display: inline-block;
                    }
                    button:hover, input[type="submit"]:hover, .btn:hover {
                        background: #005a9e;
                    }
                    .btn-danger {
                        background: #d13438;
                    }
                    .btn-danger:hover {
                        background: #a52a2a;
                    }
                    .btn-success {
                        background: #28a745;
                    }
                    .btn-success:hover {
                        background: #218838;
                    }
                    .btn-preview {
                        background: #6c757d;
                    }
                    .btn-preview:hover {
                        background: #5a6268;
                    }
                    .logout-btn {
                        background: #FFFFFF;
                        float: right;
                    }
                    .logout-btn:hover {
                        background: #a52a2a;
                    }
                    input[type="file"] {
                        margin: 10px 0;
                    }
                    .empty-state {
                        text-align: center;
                        padding: 40px;
                        color: #999;
                    }
                    .permission-notice {
                        background: #fff3cd;
                        border: 1px solid #ffc107;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                        color: #856404;
                    }
                    .modal {
                        display: none;
                        position: fixed;
                        z-index: 1000;
                        left: 0;
                        top: 0;
                        width: 100%;
                        height: 100%;
                        background-color: rgba(0,0,0,0.8);
                    }
                    .modal-content {
                        position: relative;
                        margin: 50px auto;
                        max-width: 90%;
                        max-height: 90%;
                        background: white;
                        padding: 20px;
                        border-radius: 8px;
                    }
                    .close-modal {
                        position: absolute;
                        top: 10px;
                        right: 20px;
                        font-size: 30px;
                        font-weight: bold;
                        color: #aaa;
                        cursor: pointer;
                    }
                    .close-modal:hover {
                        color: #000;
                    }
                    .preview-container {
                        max-width: 100%;
                        max-height: 80vh;
                        overflow: auto;
                        text-align: center;
                    }
                    .preview-container img {
                        max-width: 100%;
                        height: auto;
                    }
                    .preview-container iframe {
                        width: 100%;
                        height: 80vh;
                        border: none;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <a href="/logout" class="logout-btn">Logout</a>
                    <h2>🔐 SecureCloud Vault</h2>
                    
                    <div class="user-info">
                        <strong>✅ Logged in as:</strong> {{user.get('name')}}<br>
                        <strong>Email:</strong> {{user.get('preferred_username')}}<br>
                        <span class="role-badge">{{ role_display }}</span>
                    </div>

                    {% if not user_is_admin %}
                    <div class="permission-notice">
                        ℹ️ <strong>Viewer Mode:</strong> You can view and download files. Contact an administrator to upload or delete files.
                    </div>
                    {% endif %}

                    <div class="upload-section admin-only">
                        <h3>📤 Upload Document (Admin Only)</h3>
                        <form method="POST" action="/upload" enctype="multipart/form-data">
                            <input type="file" name="file" required>
                            <input type="submit" value="Upload">
                        </form>
                        <p style="color: #666; font-size: 12px; margin-top: 10px;">
                            Allowed: TXT, PDF, DOC, DOCX, PNG, JPG, JPEG (Max 16MB)
                        </p>
                    </div>

                    <div class="file-list">
                        <h3>📋 Shared Files ({{files|length}})</h3>
                        {% if files %}
                            {% for file in files %}
                                <div class="file-item">
                                    <div class="file-info">
                                        <div class="file-name">📄 {{ file.original_filename }}</div>
                                        <div class="file-meta">
                                            Uploaded by: {{ file.user_email }} | 
                                            Size: {{ format_size(file.size) }} | 
                                            Date: {{ format_date(file.upload_date) }}
                                        </div>
                                    </div>
                                    <div class="file-actions">
                                        {% if is_image(file.filename) or is_pdf(file.filename) %}
                                            <button class="btn btn-preview" onclick="previewFile('{{ file.filename }}', '{{ file.original_filename }}')">👁️ Preview</button>
                                        {% endif %}
                                        <a href="/download/{{ file.filename }}" class="btn btn-success">⬇️ Download</a>
                                        <button class="btn btn-danger admin-only" onclick="deleteFile('{{ file.filename }}', '{{ file.original_filename }}')">🗑️ Delete</button>
                                    </div>
                                </div>
                            {% endfor %}
                        {% else %}
                            <div class="empty-state">
                                <p>📭 No files uploaded yet.</p>
                                {% if user_is_admin %}
                                <p>Upload your first document above!</p>
                                {% endif %}
                            </div>
                        {% endif %}
                    </div>
                </div>

                <!-- Preview Modal -->
                <div id="previewModal" class="modal">
                    <div class="modal-content">
                        <span class="close-modal" onclick="closePreview()">&times;</span>
                        <h3 id="previewTitle"></h3>
                        <div class="preview-container" id="previewContainer"></div>
                    </div>
                </div>

                <script>
                    function deleteFile(filename, displayName) {
                        if (confirm('Are you sure you want to delete "' + displayName + '"?')) {
                            fetch('/delete/' + filename, {
                                method: 'DELETE'
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    location.reload();
                                } else {
                                    alert('Error deleting file: ' + data.error);
                                }
                            })
                            .catch(error => {
                                alert('Error deleting file');
                            });
                        }
                    }

                    function previewFile(filename, displayName) {
                        document.getElementById('previewTitle').textContent = displayName;
                        const container = document.getElementById('previewContainer');
                        
                        if (filename.match(/\\.(jpg|jpeg|png)$/i)) {
                            container.innerHTML = '<img src="/preview/' + filename + '" alt="' + displayName + '">';
                        } else if (filename.match(/\\.pdf$/i)) {
                            container.innerHTML = '<iframe src="/preview/' + filename + '"></iframe>';
                        }
                        
                        document.getElementById('previewModal').style.display = 'block';
                    }

                    function closePreview() {
                        document.getElementById('previewModal').style.display = 'none';
                        document.getElementById('previewContainer').innerHTML = '';
                    }

                    window.onclick = function(event) {
                        const modal = document.getElementById('previewModal');
                        if (event.target == modal) {
                            closePreview();
                        }
                    }

                    document.addEventListener('keydown', function(event) {
                        if (event.key === 'Escape') {
                            closePreview();
                        }
                    });
                </script>
            </body>
            </html>
        """, user=user, files=files, format_size=format_file_size, 
            format_date=format_date, is_image=is_image, is_pdf=is_pdf,
            user_is_admin=user_is_admin, role_display=role_display, role_color=role_color)

    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SecureCloud Vault - Login</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 400px;
                    margin: 100px auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    text-align: center;
                }
                h2 {
                    color: #333;
                    margin-top: 0;
                }
                .login-btn {
                    display: inline-block;
                    background: #0078d4;
                    color: white;
                    padding: 12px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                    font-size: 16px;
                }
                .login-btn:hover {
                    background: #005a9e;
                }
                .status {
                    color: #d13438;
                    font-size: 18px;
                }
                p {
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🔐 SecureCloud Vault</h2>
                <p class="status">❌ Not logged in</p>
                <p>Sign in with your Azure AD account to access shared documents.</p>
                <a href="/login" class="login-btn">🔐 Login with Azure AD</a>
            </div>
        </body>
        </html>
    """)

@app.route("/upload", methods=["POST"])
def upload_file():
    if "user" not in session:
        return redirect(url_for("home"))
    
    # Check if user is admin
    if not is_admin(session["user"]):
        return "Unauthorized: Only administrators can upload files", 403
    
    if 'file' not in request.files:
        return redirect(url_for("home"))
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(url_for("home"))
    
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        # Add username prefix and timestamp to avoid conflicts
        user_prefix = session["user"].get("preferred_username", "user").split("@")[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{user_prefix}_{timestamp}_{original_filename}"
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Save metadata
        save_file_metadata(filename, session["user"].get("preferred_username"), original_filename)
        
        return redirect(url_for("home"))
    
    return "Invalid file type", 400

@app.route("/download/<filename>")
def download_file(filename):
    if "user" not in session:
        return redirect(url_for("home"))
    
    # All authenticated users can download
    metadata = get_file_metadata(filename)
    if not metadata:
        return "File not found", 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=metadata.get('original_filename', filename))
    return "File not found", 404

@app.route("/preview/<filename>")
def preview_file(filename):
    if "user" not in session:
        return redirect(url_for("home"))
    
    # All authenticated users can preview
    metadata = get_file_metadata(filename)
    if not metadata:
        return "File not found", 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return "File not found", 404

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    if "user" not in session:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    # Check if user is admin
    if not is_admin(session["user"]):
        return jsonify({"success": False, "error": "Unauthorized: Only administrators can delete files"}), 403
    
    metadata = get_file_metadata(filename)
    if not metadata:
        return jsonify({"success": False, "error": "File not found"}), 404
    
    # Delete file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    metadata_path = os.path.join(METADATA_FOLDER, f"{filename}.json")
    
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        if os.path.exists(metadata_path):
            os.remove(metadata_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/login")
def login():
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        prompt="select_account"
    )
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    print("✅ HIT /auth/callback")
    code = request.args.get("code")
    
    if not code:
        error = request.args.get("error")
        error_desc = request.args.get("error_description")
        print(f"❌ Auth error: {error} - {error_desc}")
        return f"Auth error: {error} - {error_desc}", 400

    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    if "error" in result:
        print(f"❌ Token error: {result}")
        return f"Login failed: {result.get('error_description')}", 400

    claims = result.get("id_token_claims", {})
    
    # DEBUG: Print all claims to see what we're getting
    print("=" * 60)
    print("🔍 ALL TOKEN CLAIMS:")
    print(json.dumps(claims, indent=2))
    print("=" * 60)
    
    # Extract email
    user_email = claims.get("preferred_username", "").lower()
    print(f"📧 User email: {user_email}")
    
    # Extract roles from the token
    roles = claims.get("roles", [])
    print(f"🎭 Roles from Azure token: {roles}")
    
    # EXPLICIT ASSIGNMENT: Force admin role for your email
    if "shilpa.sureshkumar@outlook.com" in user_email:
        roles = ["Game.Lead.Admin"]
        print("✅ FORCE ASSIGNED ADMIN ROLE: Game.Lead.Admin")
    elif not roles:
        # Default to viewer if no roles in token
        roles = ["Game.Tester.Player"]
        print("✅ DEFAULT ASSIGNED VIEWER ROLE: Game.Tester.Player")
    
    session["user"] = {
        "name": claims.get("name"),
        "preferred_username": claims.get("preferred_username"),
        "oid": claims.get("oid"),
        "roles": roles
    }
    
    print(f"✅ Login successful: {claims.get('name')}")
    print(f"   📋 Final roles in session: {roles}")
    print(f"   🔐 Is admin check: {ADMIN_ROLE in roles}")
    print("=" * 60)
    
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    logout_url = f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={REDIRECT_URI.rsplit('/', 1)[0]}"
    return redirect(logout_url)

if __name__ == "__main__":
    app.run(host="localhost", port=5001, debug=True)
