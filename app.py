from flask import Flask, render_template, request, redirect, url_for, session, g, abort
from datetime import datetime
import psycopg2
import psycopg2.extras
import os
import random
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'zzzzzzzz'  
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- Database functions ---
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL)
    return g.db

def get_cursor():
    return get_db().cursor(cursor_factory=psycopg2.extras.RealDictCursor)

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Routes ---
@app.route('/')
def index():
    posts = []
    if 'user_id' in session:
        user_id = session['user_id']
        cur = get_cursor()
        query = '''
        SELECT posts.id AS id, posts.title, posts.content, posts.date, posts.image,
               users.username,
               (SELECT COUNT(*) FROM likes WHERE post_id = posts.id AND value = 'like') AS like_count,
               (SELECT COUNT(*) FROM likes WHERE post_id = posts.id AND value = 'unlike') AS unlike_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        WHERE posts.user_id = %s OR posts.user_id IN (
            SELECT user_id FROM friends WHERE friend_id = %s AND status = 'accepted'
            UNION
            SELECT friend_id FROM friends WHERE user_id = %s AND status = 'accepted'
        )
        ORDER BY posts.date DESC
        '''
        cur.execute(query, (user_id, user_id, user_id))
        posts = cur.fetchall()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        file = request.files.get('profile_pic')
        profile_pic_path = None

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join('static', 'profile_pics', filename))
            profile_pic_path = f'profile_pics/{filename}'

        cur = get_cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        existing_user = cur.fetchone()
        if existing_user:
            error = 'Username already exists.'
        else:
            cur.execute('INSERT INTO users (username, password, profile_pic) VALUES (%s, %s, %s)',
                        (username, password, profile_pic_path))
            g.db.commit()
            return redirect(url_for('login'))

    return render_template('register.html', error=error)

@app.route('/profile/<int:user_id>', methods=['GET', 'POST'])
def view_profile(user_id):
    cur = get_cursor()
    is_owner = session.get('user_id') == user_id

    if request.method == 'POST' and is_owner:
        file = request.files.get('profile_pic')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join('static', 'profile_pics', filename)
            file.save(filepath)
            cur.execute('UPDATE users SET profile_pic = %s WHERE id = %s', (f'profile_pics/{filename}', user_id))
            g.db.commit()

    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    cur.execute('SELECT * FROM posts WHERE user_id = %s ORDER BY date DESC', (user_id,))
    posts = cur.fetchall()

    return render_template('profile.html', user=user, posts=posts, is_owner=is_owner)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cur = get_cursor()
    cur.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
    post = cur.fetchone()
    if post and post['user_id'] == session['user_id']:
        cur.execute('DELETE FROM posts WHERE id = %s', (post_id,))
        g.db.commit()
    return redirect(url_for('view_profile', user_id=session['user_id']))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cur = get_cursor()
        cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cur.fetchone()
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            error = 'Invalid credentials.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/banner')
def show_random_banner():
    banner_folder = os.path.join('static', 'banners')
    images = [img for img in os.listdir(banner_folder) if img.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    if not images:
        return "No banners found."
    selected = random.choice(images)
    return render_template('banner.html', image_url=url_for('static', filename=f'banners/{selected}'))


@app.route('/new', methods=['GET', 'POST'])
def new_post():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files.get('image')
        image_filename = None

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            image_filename = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(image_filename)
            image_filename = f'uploads/{filename}'  # relative for HTML

        user_id = session.get('user_id')
        db = get_db()
        db.execute('INSERT INTO posts (title, content, date, user_id, image) VALUES (?, ?, ?, ?, ?)',
                   (title, content, datetime.now().strftime("%Y-%m-%d %H:%M"), user_id, image_filename))
        db.commit()
        return redirect(url_for('index'))

    return render_template('new.html')


@app.route('/post/<int:post_id>')
def post(post_id):
    db = get_db()
    post = db.execute('''SELECT posts.*, users.username, users.profile_pic
                         FROM posts JOIN users ON posts.user_id = users.id
                         WHERE posts.id = ?''', (post_id,)).fetchone()
    return render_template('post.html', post=post)


@app.route('/post/<int:post_id>')
def view_post(post_id):
    db = get_db()
    
    post = db.execute('''
    SELECT posts.id,
           posts.title,
           posts.content,
           posts.date,
           posts.image,
           users.username,
            users.profile_pic,
           users.id AS user_id,
           (SELECT COUNT(*) FROM likes WHERE post_id = posts.id AND value = 'like') AS like_count,
           (SELECT COUNT(*) FROM likes WHERE post_id = posts.id AND value = 'unlike') AS unlike_count
    FROM posts
    JOIN users ON posts.user_id = users.id
    WHERE posts.id = ?
''', (post_id,)).fetchone()

    if not post:
        abort(404)
    # check permission
    if post['user_id'] != session.get('user_id'):
        is_friend = db.execute('''
            SELECT 1 FROM friends WHERE
            (user_id = ? AND friend_id = ? OR friend_id = ? AND user_id = ?) AND status = 'accepted' ''',
            (session.get('user_id'), post['user_id'], session.get('user_id'), post['user_id'])).fetchone()
        if not is_friend:
            abort(403)
    return render_template('post.html', post=post)




@app.route('/add_friend/<int:user_id>')
def add_friend(user_id):
    if not session.get('logged_in') or user_id == session['user_id']:
        return redirect(url_for('index'))
    db = get_db()
    exists = db.execute('''SELECT * FROM friends WHERE
                           (user_id = ? AND friend_id = ?) OR
                           (friend_id = ? AND user_id = ?)''',
                           (session['user_id'], user_id, session['user_id'], user_id)).fetchone()
    if not exists:
        db.execute('INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, ?)',
                   (session['user_id'], user_id, 'pending'))
        db.commit()
    return redirect(url_for('friends_page'))


@app.route('/accept_friend/<int:request_id>')
def accept_friend(request_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    db = get_db()
    db.execute('UPDATE friends SET status = ? WHERE id = ? AND friend_id = ?',
               ('accepted', request_id, session['user_id']))
    db.commit()
    return redirect(url_for('friends_page'))

@app.route('/like/<int:post_id>')
def like_post(post_id):
    return handle_vote(post_id, 'like')

@app.route('/unlike/<int:post_id>')
def unlike_post(post_id):
    return handle_vote(post_id, 'unlike')

def handle_vote(post_id, vote_type):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    # Remove any existing vote by the user
    db.execute('DELETE FROM likes WHERE user_id = ? AND post_id = ?', (user_id, post_id))
    db.execute('INSERT INTO likes (user_id, post_id, value) VALUES (?, ?, ?)', (user_id, post_id, vote_type))
    db.commit()

    # Recalculate aura
    db.execute('''
        UPDATE users SET aura = (
            SELECT COUNT(*) FROM posts WHERE user_id = users.id
        ) * (
            SELECT COUNT(*) FROM likes l
            JOIN posts p ON p.id = l.post_id
            WHERE p.user_id = users.id AND l.value = 'like'
        ) - (
            SELECT COUNT(*) FROM likes l
            JOIN posts p ON p.id = l.post_id
            WHERE p.user_id = users.id AND l.value = 'unlike'
        )
    ''')
    db.commit()

    return redirect(request.referrer or url_for('index'))

@app.route('/friends', methods=['GET', 'POST'])
def friends_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    # --- 1. Search ---
    query = request.args.get('q', '')
    search_results = []
    if query:
        found_users = db.execute('SELECT id, username FROM users WHERE username LIKE ?', (f'%{query}%',)).fetchall()
        for u in found_users:
            if u['id'] == user_id:
                continue
            is_friend = db.execute('''SELECT 1 FROM friends WHERE
                                      ((user_id = ? AND friend_id = ?) OR (friend_id = ? AND user_id = ?))
                                      AND status = 'accepted' ''',
                                   (user_id, u['id'], user_id, u['id'])).fetchone()
            search_results.append({
                'id': u['id'],
                'username': u['username'],
                'is_friend': bool(is_friend)
            })

    # --- 2. Incoming friend requests ---
    pending_requests = db.execute('''
        SELECT friends.id, users.username, users.id as user_id
        FROM friends
        JOIN users ON users.id = friends.user_id
        WHERE friends.friend_id = ? AND friends.status = 'pending'
    ''', (user_id,)).fetchall()

    # --- 3. Friends list ---
    friends = db.execute('''
        SELECT users.id, users.username, users.profile_pic
        FROM users
        JOIN friends ON (
            (friends.user_id = users.id AND friends.friend_id = ?)
            OR (friends.friend_id = users.id AND friends.user_id = ?)
        )
        WHERE friends.status = 'accepted'
    ''', (user_id, user_id)).fetchall()

    return render_template('friends.html',
                           search_results=search_results,
                           query=query,
                           pending_requests=pending_requests,
                           friends=friends)

# --- Initialize DB (only run once) ---
def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL
                    )''')
        db.execute('''CREATE TABLE IF NOT EXISTS posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        date TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )''')
        db.execute('''CREATE TABLE IF NOT EXISTS friends (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        friend_id INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (friend_id) REFERENCES users(id)
                    )''')
        db.commit()

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    
    app.run(debug=True)
