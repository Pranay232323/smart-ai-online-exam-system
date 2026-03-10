from flask import Flask, render_template
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

if __name__ == "__main__":
    app.run(debug=True)