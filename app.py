from flask import Flask, render_template, request, redirect
import mysql.connector

app = Flask(__name__)

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="@Pranay23",
    database="exam_system"
)

cursor = db.cursor()

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/test-db")
def test_db():
    cursor.execute("SELECT * FROM users")
    result = cursor.fetchall()
    return str(result)
# ------Register Page-------
@app.route("/register")
def register():
    return render_template("register.html")
#------Save user to database------

@app.route("/register-user", methods=["POST"])
def register_user():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    sql = "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)"
    values = (name, email, password, "student")

    cursor.execute(sql, values)
    db.commit()

    return redirect("/")
#------login------
@app.route("/login-user", methods=["POST"])
def login_user():

    email = request.form["email"]
    password = request.form["password"]

    sql = "SELECT * FROM users WHERE email=%s AND password=%s"
    values = (email, password)

    cursor.execute(sql, values)
    user = cursor.fetchone()

    if user:
        return redirect("/dashboard")
    else:
        return "Invalid email or password"
    
#------Dashboard------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

#------admin dashboard------
@app.route("/admin-dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")

#------create exam------
@app.route("/create-exam")
def create_exam():
    return render_template("create_exam.html")

#------save exam------
@app.route("/save-exam", methods=["POST"])
def save_exam():

    title = request.form["title"]
    description = request.form["description"]
    duration = request.form["duration"]

    sql = "INSERT INTO exams (title, description, duration) VALUES (%s,%s,%s)"
    values = (title, description, duration)

    cursor.execute(sql, values)
    db.commit()

    return "Exam Created Successfully"

if __name__ == "__main__":
    app.run(debug=True)