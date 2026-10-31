import os
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from flask import (
    Flask, request, redirect, url_for,
    session, render_template_string, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

DATABASE_URL = os.environ.get("DATABASE_URL")

if not app.secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable.")

if not DATABASE_URL:
    raise RuntimeError("Set the CICOchat DATABASE_URL environment variable.")


def connect_db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def initialize_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(80) NOT NULL,
                email VARCHAR(254) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                bio VARCHAR(300) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS posts (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                body VARCHAR(2000) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS follows (
                follower_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                followed_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (follower_id, followed_id),
                CHECK (follower_id <> followed_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                sender_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                receiver_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                body VARCHAR(1000) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS posts_created_idx
                ON posts(created_at DESC);

            CREATE INDEX IF NOT EXISTS messages_conversation_idx
                ON messages(sender_id, receiver_id, created_at);
        """)


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1769e0">
<title>{{ title }} — CICOchat</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f3f6fb;color:#172033;font-family:Arial,sans-serif}
header{background:#1769e0;color:white;padding:18px;text-align:center;font-size:25px;font-weight:bold}
nav{background:white;padding:13px;text-align:center;border-bottom:1px solid #ddd}
nav a{color:#1769e0;text-decoration:none;margin:5px 7px;font-weight:bold}
main{max-width:620px;margin:20px auto;padding:0 12px}
.card{background:white;border-radius:13px;padding:17px;margin-bottom:15px;box-shadow:0 2px 8px #0000000b}
input,textarea{width:100%;padding:12px;margin:7px 0;border:1px solid #ccd3df;border-radius:8px;font-size:16px}
button,.button{background:#1769e0;color:white;border:0;border-radius:9px;padding:12px 16px;font-size:15px;cursor:pointer;display:inline-block;text-decoration:none}
.secondary{background:#e7efff;color:#174da3}
.muted,small{color:#68758a}
.post{white-space:pre-wrap;overflow-wrap:anywhere}
footer{text-align:center;padding:25px;color:#68758a}
</style>
</head>
<body>
<header>CICOchat</header>
<nav>
<a href="{{ url_for('home') }}">Home</a>
{% if user %}
<a href="{{ url_for('people') }}">People</a>
<a href="{{ url_for('inbox') }}">Messages</a>
<a href="{{ url_for('profile') }}">My Profile</a>
<a href="{{ url_for('logout') }}">Log out</a>
{% else %}
<a href="{{ url_for('login') }}">Log in</a>
<a href="{{ url_for('register') }}">Join</a>
{% endif %}
</nav>
<main>
{% for message in get_flashed_messages() %}
<div class="card">{{ message }}</div>
{% endfor %}
{{ content|safe }}
</main>
<footer>CICOchat — Connect, share and communicate.</footer>
<script>
function startVoice(inputId) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
        alert("Voice input is not supported by this browser.");
        return;
    }
    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = function(event) {
        const field = document.getElementById(inputId);
        if (field) {
            const spoken = event.results[0][0].transcript;
            field.value = (field.value ? field.value + " " : "") + spoken;
            field.focus();
        }
    };
    recognition.onerror = function() {
        alert("Voice input failed. Check microphone permission and try again.");
    };
    recognition.start();
}
</script>
</body>
</html>
"""


def page(title, content):
    user = None
    if session.get("user_id"):
        with connect_db() as db:
            user = db.execute(
                "SELECT id, name, email, bio FROM users WHERE id = %s",
                (session["user_id"],)
            ).fetchone()
    return render_template_string(PAGE, title=title, content=content, user=user)


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    with connect_db() as db:
        posts = db.execute("""
            SELECT posts.body, posts.created_at, users.name
            FROM posts JOIN users ON users.id = posts.user_id
            ORDER BY posts.id DESC LIMIT 50
        """).fetchall()

    if session.get("user_id"):
        content = """
        <section class="card"><h3>What's on your mind?</h3>
        <form method="post" action="/post">
        <textarea id="postbody" name="body" maxlength="2000"
        placeholder="Write a post..." required></textarea>
        <button type="button" class="secondary"
        onclick="startVoice('postbody')">🎙️ Speak</button>
        <button type="submit">Publish post</button>
        </form></section>
        """
    else:
        content = """
        <section class="card"><h2>Welcome to CICOchat!</h2>
        <p>Connect with people, share your thoughts and make friends.</p>
        <a class="button" href="/register">Create an account</a>
        <a class="button secondary" href="/login">Log in</a>
        </section>
        """

    content += "<h2>Latest posts</h2>"
    if posts:
        for post in posts:
            content += """
            <article class="card">
            <strong>{}</strong>
            <p class="post">{}</p>
            <small>{}</small>
            </article>
            """.format(
                post["name"],
                # Escape user content so it cannot inject HTML.
                __import__("html").escape(post["body"]),
                post["created_at"]
            )
    else:
        content += '<section class="card">No posts yet. Be the first!</section>'

    return page("Home", content)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        email = request.form.get("email", "").strip().lower()[:254]
        password = request.form.get("password", "")

        if not name or "@" not in email or len(password) < 8:
            flash("Enter your name, a valid email and a password of at least 8 characters.")
        else:
            try:
                with connect_db() as db:
                    db.execute(
                        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                        (name, email, generate_password_hash(password))
                    )
                flash("Account created. You can now log in.")
                return redirect(url_for("login"))
            except psycopg.errors.UniqueViolation:
                flash("That email already has an account.")

    content = """
    <section class="card"><h2>Create your account</h2>
    <form method="post">
    <input name="name" placeholder="Your name" maxlength="80" required>
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" minlength="8"
    placeholder="Password (at least 8 characters)" required>
    <button type="submit">Register</button>
    </form></section>
    """
    return page("Register", content)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with connect_db() as db:
            user = db.execute(
                "SELECT id, password FROM users WHERE email = %s",
                (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))

        flash("Email or password is incorrect.")

    content = """
    <section class="card"><h2>Log in</h2>
    <form method="post">
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" placeholder="Password" required>
    <button type="submit">Log in</button>
    </form></section>
    """
    return page("Login", content)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/post", methods=["POST"])
@login_required
def create_post():
    body = request.form.get("body", "").strip()
    if body and len(body) <= 2000:
        with connect_db() as db:
            db.execute(
                "INSERT INTO posts (user_id, body) VALUES (%s, %s)",
                (session["user_id"], body)
            )
    return redirect(url_for("home"))


@app.route("/people")
@login_required
def people():
    with connect_db() as db:
        users = db.execute(
            "SELECT id, name, bio FROM users WHERE id <> %s ORDER BY name",
            (session["user_id"],)
        ).fetchall()
        following = {
            row["followed_id"] for row in db.execute(
                "SELECT followed_id FROM follows WHERE follower_id = %s",
                (session["user_id"],)
            ).fetchall()
        }

    import html
    content = "<section class='card'><h2>People</h2>"
    if not users:
        content += "<p>You're among the first members!</p>"

    for person in users:
        name = html.escape(person["name"])
        bio = html.escape(person["bio"] or "")
        content += "<p><strong>{}</strong><br>{}<br>".format(name, bio)

        if person["id"] in following:
            content += "<span class='muted'>Following</span>"
        else:
            content += (
                '<form method="post" action="/follow/{}">'
                '<button>Follow</button></form>'.format(person["id"])
            )
        content += "</p><hr>"

    content += "</section>"
    return page("People", content)


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow(user_id):
    if user_id != session["user_id"]:
        with connect_db() as db:
            exists = db.execute(
                "SELECT id FROM users WHERE id = %s", (user_id,)
            ).fetchone()
            if exists:
                db.execute(
                    "INSERT INTO follows (follower_id, followed_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (session["user_id"], user_id)
                )
    return redirect(url_for("people"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        bio = request.form.get("bio", "").strip()[:300]
        with connect_db() as db:
            db.execute(
                "UPDATE users SET bio = %s WHERE id = %s",
                (bio, session["user_id"])
            )
        flash("Profile updated.")
        return redirect(url_for("profile"))

    with connect_db() as db:
        user = db.execute(
            "SELECT name, email, bio FROM users WHERE id = %s",
            (session["user_id"],)
        ).fetchone()

    import html
    content = """
    <section class="card"><h2>My Profile</h2>
    <p><strong>Name:</strong> {}</p>
    <p><strong>Email:</strong> {}</p>
    <form method="post">
    <textarea name="bio" maxlength="300"
    placeholder="Tell people about yourself">{}</textarea>
    <button type="submit">Save profile</button>
    </form></section>
    """.format(
        html.escape(user["name"]),
        html.escape(user["email"]),
        html.escape(user["bio"] or "")
    )
    return page("My Profile", content)


@app.route("/messages")
@login_required
def inbox():
    with connect_db() as db:
        users = db.execute(
            "SELECT id, name FROM users WHERE id <> %s ORDER BY name",
            (session["user_id"],)
        ).fetchall()

    import html
    content = "<section class='card'><h2>Messages</h2>"
    content += "<p>Choose a member to open a conversation.</p>"
    for person in users:
        content += '<p><a href="/chat/{}">{}</a></p>'.format(
            person["id"], html.escape(person["name"])
        )
    content += "</section>"
    return page("Messages", content)


@app.route("/chat/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat(user_id):
    me = session["user_id"]

    with connect_db() as db:
        other = db.execute(
            "SELECT id, name FROM users WHERE id = %s", (user_id,)
        ).fetchone()

        if not other or user_id == me:
            flash("Member not found.")
            return redirect(url_for("inbox"))

        if request.method == "POST":
            body = request.form.get("body", "").strip()
            if body and len(body) <= 1000:
                db.execute(
                    "INSERT INTO messages (sender_id, receiver_id, body) "
                    "VALUES (%s, %s, %s)",
                    (me, user_id, body)
                )
            return redirect(url_for("chat", user_id=user_id))

        messages = db.execute("""
            SELECT messages.body, messages.created_at, users.name
            FROM messages JOIN users ON users.id = messages.sender_id
            WHERE (sender_id = %s AND receiver_id = %s)
               OR (sender_id = %s AND receiver_id = %s)
            ORDER BY messages.id ASC LIMIT 100
        """, (me, user_id, user_id, me)).fetchall()

    import html
    content = "<section class='card'><h2>Chat with {}</h2>".format(
        html.escape(other["name"])
    )

    for message in messages:
        content += "<p><strong>{}:</strong> <span class='post'>{}</span></p>".format(
            html.escape(message["name"]),
            html.escape(message["body"])
        )

    content += """
    <form method="post">
    <textarea id="messagebody" name="body" maxlength="1000"
    placeholder="Write a message..." required></textarea>
    <button type="button" class="secondary"
    onclick="startVoice('messagebody')">🎙️ Speak</button>
    <button type="submit">➤ Send</button>
    </form></section>
    """
    return page("Messages", content)


@app.route("/health")
def health():
    return {"status": "ok", "app": "CICOchat"}


@app.route("/privacy")
def privacy():
    return page("Privacy", """
    <section class="card">
    <h2>Privacy information</h2>
    <p>This is an early development version. Do not use it for sensitive information.
    Privacy and security terms must be reviewed before public launch.</p>
    </section>
    """)


if __name__ == "__main__":
    initialize_db()
    app.run(debug=False)
