import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = "change-me-later"

UPLOAD_DIR = os.path.join(app.static_folder, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---- Temporary in-memory "database" ----
# Now stores: { "username": {"password_hash": "...", "contact": "..."} }
users_store = {}
items_store = []

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def current_user():
    return session.get('username')

def require_login():
    if not current_user():
        return jsonify({'error': 'Login required'}), 401
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

@app.route('/')
def index():
    return app.send_static_file('index.html')

# ---------------- Auth ----------------

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    contact = (data.get('contact') or '').strip()

    if not username or not password or not contact:
        return jsonify({'error': 'Username, password, and contact number are required'}), 400
    if username in users_store:
        return jsonify({'error': 'Username already taken'}), 400

    # ✅ Store both password and contact number
    users_store[username] = {
        'password_hash': generate_password_hash(password),
        'contact': contact
    }
    return jsonify({'ok': True})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user_data = users_store.get(username)
    # ✅ Check password against the new dictionary structure
    if user_data and check_password_hash(user_data['password_hash'], password):
        session['username'] = username
        return jsonify({'ok': True, 'username': username})
    return jsonify({'error': 'Invalid username or password'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('username', None)
    return jsonify({'ok': True})

@app.route('/api/me')
def api_me():
    return jsonify({'username': current_user()})

# ---------------- Items ----------------

def public_item(item):
    return {k: v for k, v in item.items() if k != 'contact'}

@app.route('/api/items', methods=['GET'])
def list_items():
    sorted_items = sorted(items_store, key=lambda i: i['created_at'], reverse=True)
    return jsonify([public_item(i) for i in sorted_items])

@app.route('/api/items/<item_id>/contact', methods=['GET'])
def get_contact(item_id):
    auth_error = require_login()
    if auth_error:
        return auth_error

    item = next((i for i in items_store if i['item_id'] == item_id), None)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    # ✅ Look up the owner's contact number from the users_store
    owner_username = item['owner']
    user_data = users_store.get(owner_username, {})
    contact_info = user_data.get('contact', 'No contact info provided')
    
    return jsonify({
        'contact': contact_info,
        'owner': owner_username
    })

@app.route('/api/items', methods=['POST'])
def create_item():
    auth_error = require_login()
    if auth_error:
        return auth_error

    form = request.form
    # ✅ Removed 'contact' from required fields since it's now tied to the user account
    required = ['title', 'type', 'category', 'location', 'date', 'description']
    if not all(form.get(f) for f in required):
        return jsonify({'error': 'All fields are required'}), 400

    photo_url = None
    photo = request.files.get('photo')
    if photo and photo.filename and allowed_file(photo.filename):
        filename = f"{uuid.uuid4().hex}_{secure_filename(photo.filename)}"
        photo.save(os.path.join(UPLOAD_DIR, filename))
        photo_url = f"/uploads/{filename}"

    item = {
        'item_id': uuid.uuid4().hex,
        'owner': current_user(),
        'type': form['type'],
        'title': form['title'],
        'category': form['category'],
        'description': form['description'],
        'location': form['location'],
        'date': form['date'],
        'status': 'open',
        'photo_url': photo_url,
        'created_at': datetime.utcnow().isoformat()
    }
    items_store.append(item)
    return jsonify(item)

@app.route('/api/items/<item_id>/resolve', methods=['POST'])
def resolve_item(item_id):
    auth_error = require_login()
    if auth_error:
        return auth_error

    for item in items_store:
        if item['item_id'] == item_id:
            if item['owner'] != current_user():
                return jsonify({'error': 'Only the poster can resolve this item'}), 403
            item['status'] = 'resolved'
            return jsonify(item)
    return jsonify({'error': 'Item not found'}), 404

@app.route('/api/items/<item_id>/claim', methods=['POST'])
def claim_item(item_id):
    auth_error = require_login()
    if auth_error:
        return auth_error

    for item in items_store:
        if item['item_id'] == item_id:
            if item['owner'] != current_user():
                return jsonify({'error': 'Only the poster can claim this item'}), 403
            # Change status to 'claimed' instead of deleting it
            item['status'] = 'claimed'
            return jsonify(item)
    return jsonify({'error': 'Item not found'}), 404


@app.route('/api/items/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    auth_error = require_login()
    if auth_error:
        return auth_error

    item = next((i for i in items_store if i['item_id'] == item_id), None)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    if item['owner'] != current_user():
        return jsonify({'error': 'Only the poster can delete this item'}), 403

    items_store[:] = [i for i in items_store if i['item_id'] != item_id]
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)