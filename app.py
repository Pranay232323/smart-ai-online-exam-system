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

if __name__ == "__main__":
    app.run(debug=True)