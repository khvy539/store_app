from flask import Flask, render_template, request, redirect, session, flash
import psycopg2, os
from ortools.sat.python import cp_model

app = Flask(__name__)
app.secret_key = "secret"

# ================= DB =================
def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

# ================= AIシフト =================
def generate_shift(users, shifts):

    model = cp_model.CpModel()
    n = len(users)
    x = [model.NewBoolVar(f"x{i}") for i in range(n)]

    # 2〜3人
    model.Add(sum(x) >= 2)
    model.Add(sum(x) <= 3)

    # 一般 or 管理者 必須
    model.Add(sum(
        x[i] for i,u in enumerate(users)
        if u["level"]=="general" or u["role"]=="admin"
    ) >= 1)

    # 希望者のみ
    available_ids = [s["user_id"] for s in shifts]
    for i,u in enumerate(users):
        if u["id"] not in available_ids:
            model.Add(x[i] == 0)

    solver = cp_model.CpSolver()
    solver.Solve(model)

    result = [users[i] for i in range(n) if solver.Value(x[i]) == 1]

    # ビギナーのみ禁止
    if all(u["level"] != "general" for u in result):
        return []

    return result

# ================= 認証 =================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db = get_db(); cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s",
                    (request.form["username"], request.form["password"]))
        user = cur.fetchone()
        cur.close(); db.close()

        if user:
            if user[5] == 1:
                session["user_id"] = user[0]
                session["role"] = user[4]
                flash("ログイン成功","success")
                return redirect("/")
            else:
                flash("承認待ち","warning")
        else:
            flash("ログイン失敗","danger")

        return redirect("/login")

    return render_template("login.html")

# ================= 登録 =================
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        db = get_db(); cur = db.cursor()
        cur.execute("""
            INSERT INTO users (username,password,name,role,approved,level,skill)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,(
            request.form["username"],
            request.form["password"],
            request.form["name"],
            "user",0,
            request.form["level"],
            "a"
        ))
        db.commit(); cur.close(); db.close()

        flash("登録申請しました","success")
        return redirect("/login")

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("home.html")

# ================= 在庫 =================
@app.route("/inventory")
def inventory():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    cur.close(); db.close()
    return render_template("inventory.html", products=products)

@app.route("/add_product", methods=["GET","POST"])
def add_product():
    if session.get("role") != "admin":
        return "権限なし"

    if request.method == "POST":
        db = get_db(); cur = db.cursor()
        cur.execute("""
            INSERT INTO products (name,stock,threshold)
            VALUES (%s,%s,%s)
        """,(
            request.form["name"],
            request.form["stock"],
            request.form["threshold"]
        ))
        db.commit(); cur.close(); db.close()

        flash("商品追加","success")
        return redirect("/inventory")

    return render_template("add_product.html")

# ================= シフト =================
@app.route("/shift")
def shift():
    db = get_db(); cur = db.cursor()

    cur.execute("""
        SELECT shifts.*, users.name
        FROM shifts
        JOIN users ON shifts.user_id = users.id
    """)
    shifts = cur.fetchall()

    cur.execute("SELECT * FROM generated_shifts")
    generated = cur.fetchall()

    cur.close(); db.close()
    return render_template("shift.html", shifts=shifts, generated=generated)

@app.route("/add_shift", methods=["GET","POST"])
def add_shift():
    if request.method == "POST":
        db = get_db(); cur = db.cursor()
        cur.execute("""
            INSERT INTO shifts (user_id,date,start,end)
            VALUES (%s,%s,%s,%s)
        """,(
            session["user_id"],
            request.form["date"],
            request.form["start"],
            request.form["end"]
        ))
        db.commit(); cur.close(); db.close()

        flash("シフト登録","success")
        return redirect("/shift")

    return render_template("add_shift.html")

# ================= AI生成 =================
@app.route("/generate_shift")
def generate_shift_route():
    db = get_db(); cur = db.cursor()

    cur.execute("SELECT * FROM users WHERE approved=1")
    users_raw = cur.fetchall()

    cur.execute("SELECT * FROM shifts")
    shifts_raw = cur.fetchall()

    users = [{"id":u[0],"name":u[3],"role":u[4],"level":u[6]} for u in users_raw]
    shifts = [{"user_id":s[1],"date":s[2]} for s in shifts_raw]

    result = generate_shift(users, shifts)

    if not result:
        flash("シフト生成不可","danger")
        return redirect("/shift")

    names = ",".join([u["name"] for u in result])

    cur.execute("INSERT INTO generated_shifts (date,members) VALUES (%s,%s)",
                (shifts[0]["date"], names))

    db.commit(); cur.close(); db.close()

    flash("シフト自動生成","success")
    return redirect("/shift")

# ================= ユーザー =================
@app.route("/approve")
def approve():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE approved=0")
    users = cur.fetchall()
    cur.close(); db.close()
    return render_template("approve.html", users=users)

@app.route("/approve_user/<int:id>")
def approve_user(id):
    db = get_db(); cur = db.cursor()
    cur.execute("UPDATE users SET approved=1 WHERE id=%s",(id,))
    db.commit(); cur.close(); db.close()

    flash("承認完了","success")
    return redirect("/")

@app.route("/users")
def users():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id,name,role,approved FROM users")
    users = cur.fetchall()
    cur.close(); db.close()
    return render_template("users.html", users=users)

# ================= 起動 =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
