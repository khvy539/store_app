from flask import Flask, render_template, request, redirect, session
import sqlite3, os

app = Flask(__name__)
app.secret_key = "secret"

def get_db():
    return sqlite3.connect("database.db")

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT,
        approved INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        stock REAL,
        threshold REAL
    );

    CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        start TEXT,
        end TEXT,
        status TEXT
    );
    """)
    db.commit()

    # 初期管理者（承認済）
    db.execute("INSERT OR IGNORE INTO users (id, username, password, role, approved) VALUES (1, 'admin', 'admin', 'admin', 1)")
    db.commit()
    db.close()

# ---------------- ログイン ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (request.form["username"], request.form["password"])
        ).fetchone()
        db.close()

        if user:
            if user[4] == 1:
                session["user_id"] = user[0]
                session["role"] = user[3]
                return redirect("/")
            else:
                return "承認待ちです"

    return render_template("login.html")

# ---------------- 登録 ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
            (request.form["username"], request.form["password"], "user", 0)
        )
        db.commit()
        db.close()
        return redirect("/login")

    return render_template("register.html")

# ---------------- ログアウト ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- ホーム ----------------
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("home.html")

# ---------------- 在庫 ----------------
@app.route("/inventory")
def inventory():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    db.close()
    return render_template("inventory.html", products=products)

@app.route("/add_product", methods=["GET","POST"])
def add_product():
    if session.get("role") != "admin":
        return "権限がありません"

    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO products (name, stock, threshold) VALUES (?, ?, ?)",
            (request.form["name"], request.form["stock"], request.form["threshold"])
        )
        db.commit()
        db.close()
        return redirect("/inventory")

    return render_template("add_product.html")

# ---------------- シフト ----------------
@app.route("/shift")
def shift():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    if session["role"] == "admin":
        shifts = db.execute("""
            SELECT shifts.*, users.username
            FROM shifts JOIN users ON shifts.user_id = users.id
        """).fetchall()
    else:
        shifts = db.execute(
            "SELECT * FROM shifts WHERE user_id=?",
            (session["user_id"],)
        ).fetchall()

    db.close()
    return render_template("shift.html", shifts=shifts)

@app.route("/add_shift", methods=["GET","POST"])
def add_shift():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO shifts (user_id, date, start, end, status) VALUES (?, ?, ?, ?, ?)",
            (session["user_id"], request.form["date"],
             request.form["start"], request.form["end"], "希望")
        )
        db.commit()
        db.close()
        return redirect("/shift")

    return render_template("add_shift.html")

# ---------------- 承認 ----------------
@app.route("/approve")
def approve():
    if session.get("role") != "admin":
        return "権限なし"

    db = get_db()
    users = db.execute("SELECT * FROM users WHERE approved=0").fetchall()
    db.close()
    return render_template("approve.html", users=users)

@app.route("/approve_user/<int:user_id>")
def approve_user(user_id):
    if session.get("role") != "admin":
        return "権限なし"

    db = get_db()
    db.execute("UPDATE users SET approved=1 WHERE id=?", (user_id,))
    db.commit()
    db.close()
    return redirect("/approve")

# ---------------- 起動 ----------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
    date = request.args.get("date")