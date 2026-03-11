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

    cursor.execute("SELECT * FROM exams")
    exams = cursor.fetchall()

    return render_template("dashboard.html", exams=exams)

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

#------add question------
@app.route("/add-question")
def add_question():
    return render_template("add_questions.html")

#------save question------
@app.route("/save-question", methods=["POST"])
def save_question():
    exam_id = request.form["exam_id"]
    question = request.form["question"]
    option_a = request.form["option_a"]
    option_b = request.form["option_b"]
    option_c = request.form["option_c"]
    option_d = request.form["option_d"]
    correct_answer = request.form["correct_answer"]

    sql = """
    INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """

    values = (exam_id, question, option_a, option_b, option_c, option_d, correct_answer)

    cursor.execute(sql, values)
    db.commit()

    return "Question Added Successfully"

#------Start exam------
@app.route("/start-exam/<int:exam_id>")
def start_exam(exam_id):

    cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = cursor.fetchall()

    print(questions)   # DEBUG LINE

    return render_template("exam.html", questions=questions)

#------submit exam------
@app.route("/submit-exam", methods=["POST"])
def submit_exam():

    student_id = 2
    exam_id = 1

    cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = cursor.fetchall()

    score = 0

    for q in questions:

        qid = q[0]
        correct_answer = q[7]

        student_answer = request.form.get(f"q{qid}")

        if student_answer == correct_answer:
            score += 1

    total_questions = len(questions)

    percentage = (score / total_questions) * 100

    sql = """
    INSERT INTO results (student_id, exam_id, score, total_questions)
    VALUES (%s, %s, %s, %s)
    """

    cursor.execute(sql, (student_id, exam_id, score, total_questions))
    db.commit()

    return render_template(
        "result.html",
        score=score,
        total=total_questions,
        percentage=percentage
    )



if __name__ == "__main__":
    app.run(debug=True)

