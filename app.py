import os

from flask import Flask, flash, jsonify, redirect, render_template, request, session
import mysql.connector
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv:
    load_dotenv()


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


app = Flask(__name__)
app.secret_key = require_env("SECRET_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": require_env("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "exam_system"),
}

db = mysql.connector.connect(**DB_CONFIG)
cursor = db.cursor()


def get_cursor():
    return db.cursor(buffered=True)


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def is_hashed_password(password):
    return password.startswith("pbkdf2:") or password.startswith("scrypt:")


def verify_password(stored_password, plain_password):
    if stored_password and is_hashed_password(stored_password):
        return check_password_hash(stored_password, plain_password), False

    if stored_password == plain_password:
        return True, True

    return False, False


def get_current_user_id():
    return session.get("user_id")


def get_current_user_role():
    return session.get("user_role")


def require_login():
    if not get_current_user_id():
        return redirect("/")
    return None


def require_student():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    if get_current_user_role() != "student":
        return redirect("/admin-dashboard")
    return None


def require_admin():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    if get_current_user_role() != "admin":
        return redirect("/dashboard")
    return None


def get_student_chatbot_context(student_id):
    context = {
        "student_id": student_id,
        "exam_count": 0,
        "exam_titles": [],
        "attempt_count": 0,
        "latest_result": None,
        "top_score_percentage": None,
    }

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)

    try:
        local_cursor.execute("SELECT title FROM exams ORDER BY id DESC")
        exams = local_cursor.fetchall()
        context["exam_titles"] = [row[0] for row in exams]
        context["exam_count"] = len(exams)

        local_cursor.execute(
            """
            SELECT exams.title, results.score, results.total_questions
            FROM results
            JOIN exams ON exams.id = results.exam_id
            WHERE results.student_id = %s
            ORDER BY results.id DESC
            LIMIT 1
            """,
            (student_id,),
        )
        context["latest_result"] = local_cursor.fetchone()

        local_cursor.execute(
            "SELECT COUNT(*) FROM results WHERE student_id = %s",
            (student_id,),
        )
        context["attempt_count"] = local_cursor.fetchone()[0]

        local_cursor.execute(
            """
            SELECT MAX((score / total_questions) * 100)
            FROM results
            WHERE student_id = %s AND total_questions > 0
            """,
            (student_id,),
        )
        top_score = local_cursor.fetchone()[0]
        context["top_score_percentage"] = (
            float(top_score) if top_score is not None else None
        )
    except mysql.connector.Error:
        pass
    finally:
        local_cursor.close()
        local_db.close()

    return context


def generate_student_chatbot_reply(message, student_id):
    text = (message or "").strip().lower()
    context = get_student_chatbot_context(student_id)

    if not text:
        return (
            "Ask me about available exams, starting an exam, exam history, "
            "leaderboard, exam timer, submitting answers, or tab switching rules."
        )

    if any(
        keyword in text
        for keyword in ["how many exams", "available exams", "how many exam", "exam count"]
    ):
        if context["exam_count"] == 0:
            return "There are no exams available right now."

        preview = ", ".join(context["exam_titles"][:3])
        if context["exam_count"] > 3:
            preview += ", and more"

        return (
            f"There are {context['exam_count']} exams available right now. "
            f"Some of them are: {preview}."
        )

    if any(
        keyword in text
        for keyword in ["latest result", "last result", "recent score", "my last exam"]
    ):
        latest_result = context["latest_result"]
        if not latest_result:
            return "You have not completed any exams yet, so there is no latest result to show."

        title, score, total_questions = latest_result
        percentage = (score / total_questions * 100) if total_questions else 0
        return (
            f"Your latest recorded result is for {title}. "
            f"You scored {score} out of {total_questions}, which is {percentage:.2f}%."
        )

    if any(
        keyword in text
        for keyword in ["attempt", "attempted", "how many tests", "how many exams did i take"]
    ):
        return f"You have {context['attempt_count']} recorded exam attempt(s) so far."

    if any(keyword in text for keyword in ["best score", "top score", "highest score"]):
        if context["top_score_percentage"] is None:
            return "You do not have a recorded best score yet because no completed exam was found."

        return f"Your best recorded percentage so far is {context['top_score_percentage']:.2f}%."

    faq_responses = [
        (
            ["hello", "hi", "hey"],
            (
                "Hello! I can help with basic questions about your student dashboard, "
                "exams, results, history, and leaderboard."
            ),
        ),
        (
            ["available exam", "exam list", "which exams", "show exams"],
            (
                "The Student Dashboard shows all available exams. Use the Start Exam "
                "button beside an exam title to begin."
            ),
        ),
        (
            ["start exam", "begin exam", "take exam"],
            (
                "To start an exam, go to the Student Dashboard and click Start Exam "
                "next to the exam you want to take."
            ),
        ),
        (
            ["timer", "time limit", "duration", "time remaining"],
            (
                "Each exam uses the duration set by the admin. Once the timer reaches "
                "zero, the exam is submitted automatically."
            ),
        ),
        (
            ["submit", "submit exam", "finish exam"],
            (
                "You can submit from the exam page using the Submit Exam button. "
                "The system may also auto-submit when time runs out or if tab switching is detected."
            ),
        ),
        (
            ["tab", "switch tab", "cheat", "warning", "reload", "refresh"],
            (
                "During an exam, tab switching and page reload are restricted. "
                "If the system detects a tab switch, it can auto-submit the exam."
            ),
        ),
        (
            ["result", "score", "marks", "percentage"],
            (
                "After submitting an exam, the result page shows your score, total questions, "
                "percentage, and an answer review section."
            ),
        ),
        (
            ["history", "exam history", "past exams", "previous exams"],
            "Open My Exam History from the dashboard to view your previous exam attempts and scores.",
        ),
        (
            ["leaderboard", "rank", "top students"],
            "Open the Leaderboard from the dashboard to see the top scores and rankings.",
        ),
        (
            ["dashboard", "student dashboard", "home page"],
            (
                "The Student Dashboard lists available exams and gives you quick links to "
                "Exam History and the Leaderboard."
            ),
        ),
        (
            ["login", "register", "sign up", "account"],
            (
                "New students can register from the registration page, then log in using "
                "their email and password."
            ),
        ),
    ]

    for keywords, response in faq_responses:
        if any(keyword in text for keyword in keywords):
            return response

    return (
        "I can help with basic website questions. Try asking about starting an exam, "
        "exam timer, exam history, leaderboard, results, or dashboard navigation."
    )


def create_exam_activity(student_id, exam_id):
    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    try:
        local_cursor.execute(
            """
            INSERT INTO exam_activity (student_id, exam_id, status, warning_count)
            VALUES (%s, %s, %s, %s)
            """,
            (student_id, exam_id, "In Progress", 0),
        )
        local_db.commit()
    except mysql.connector.Error:
        local_db.rollback()
    finally:
        local_cursor.close()
        local_db.close()


def update_exam_activity(student_id, exam_id, status=None, increment_warning=False):
    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    try:
        local_cursor.execute(
            """
            SELECT id, warning_count
            FROM exam_activity
            WHERE student_id = %s AND exam_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (student_id, exam_id),
        )
        activity = local_cursor.fetchone()

        if not activity:
            create_exam_activity(student_id, exam_id)
            local_cursor.execute(
                """
                SELECT id, warning_count
                FROM exam_activity
                WHERE student_id = %s AND exam_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (student_id, exam_id),
            )
            activity = local_cursor.fetchone()

        if not activity:
            return

        activity_id, warning_count = activity
        new_warning_count = warning_count + 1 if increment_warning else warning_count
        new_status = status if status else "In Progress"

        local_cursor.execute(
            """
            UPDATE exam_activity
            SET status = %s, warning_count = %s
            WHERE id = %s
            """,
            (new_status, new_warning_count, activity_id),
        )
        local_db.commit()
    except mysql.connector.Error:
        local_db.rollback()
    finally:
        local_cursor.close()
        local_db.close()


@app.route("/")
def home():
    session.clear()
    return render_template("login.html")


@app.route("/test-db")
def test_db():
    cursor.execute("SELECT * FROM users")
    result = cursor.fetchall()
    return str(result)


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")


@app.route("/forgot-password-request", methods=["POST"])
def forgot_password_request():
    email = request.form["email"].strip().lower()

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)

    try:
        local_cursor.execute("SELECT id, email FROM users WHERE email = %s", (email,))
        user = local_cursor.fetchone()

        if not user:
            flash("No account was found with that email address.", "error")
            return render_template("forgot_password.html", form_data={"email": email})

        session["password_reset_email"] = user[1]
        flash("Email verified. Please set your new password.", "success")
        return redirect("/reset-password")
    finally:
        local_cursor.close()
        local_db.close()


@app.route("/reset-password")
def reset_password():
    reset_email = session.get("password_reset_email")
    if not reset_email:
        flash("Please verify your email first.", "error")
        return redirect("/forgot-password")

    return render_template("reset_password.html", reset_email=reset_email)


@app.route("/reset-password-save", methods=["POST"])
def reset_password_save():
    reset_email = session.get("password_reset_email")
    if not reset_email:
        flash("Please verify your email first.", "error")
        return redirect("/forgot-password")

    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    if len(password) < 6:
        flash("Password must be at least 6 characters long.", "error")
        return render_template("reset_password.html", reset_email=reset_email)

    if password != confirm_password:
        flash("Password and confirm password do not match.", "error")
        return render_template("reset_password.html", reset_email=reset_email)

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)

    try:
        local_cursor.execute(
            "UPDATE users SET password = %s WHERE email = %s",
            (generate_password_hash(password), reset_email),
        )
        local_db.commit()
    finally:
        local_cursor.close()
        local_db.close()

    session.pop("password_reset_email", None)
    flash("Password reset successful. Please log in with your new password.", "success")
    return redirect("/")


@app.route("/register-user", methods=["POST"])
def register_user():
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    if len(password) < 6:
        flash("Password must be at least 6 characters long.", "error")
        return render_template("register.html", form_data={"name": name, "email": email})

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)

    try:
        local_cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing_user = local_cursor.fetchone()
        if existing_user:
            flash("An account with this email already exists.", "error")
            return render_template(
                "register.html", form_data={"name": name, "email": email}
            )

        hashed_password = generate_password_hash(password)
        local_cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_password, "student"),
        )
        local_db.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect("/")
    finally:
        local_cursor.close()
        local_db.close()


@app.route("/login-user", methods=["POST"])
def login_user():
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)

    try:
        local_cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = local_cursor.fetchone()

        if not user:
            flash("Invalid email or password.", "error")
            return render_template("login.html", form_data={"email": email})

        password_is_valid, should_upgrade = verify_password(user[3], password)
        if not password_is_valid:
            flash("Invalid email or password.", "error")
            return render_template("login.html", form_data={"email": email})

        if should_upgrade:
            upgraded_password = generate_password_hash(password)
            local_cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (upgraded_password, user[0]),
            )
            local_db.commit()

        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_email"] = user[2]
        session["user_role"] = user[4]

        if user[4] == "admin":
            return redirect("/admin-dashboard")
        return redirect("/dashboard")
    finally:
        local_cursor.close()
        local_db.close()


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    redirect_response = require_student()
    if redirect_response:
        return redirect_response

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    local_cursor.execute("SELECT * FROM exams")
    exams = local_cursor.fetchall()
    local_cursor.close()
    local_db.close()

    return render_template(
        "dashboard.html",
        exams=exams,
        student_name=session.get("user_name", "Student"),
    )


@app.route("/student-chatbot", methods=["POST"])
def student_chatbot():
    redirect_response = require_student()
    if redirect_response:
        return jsonify({"reply": "Please log in again to continue."}), 401

    message = request.form.get("message")

    if message is None and request.is_json:
        payload = request.get_json(silent=True) or {}
        message = payload.get("message", "")

    reply = generate_student_chatbot_reply(message, student_id=get_current_user_id())
    return jsonify({"reply": reply})


@app.route("/admin-dashboard")
def admin_dashboard():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template("admin_dashboard.html")


@app.route("/create-exam")
def create_exam():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template("create_exam.html")


@app.route("/save-exam", methods=["POST"])
def save_exam():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    title = request.form["title"]
    description = request.form["description"]
    duration = request.form["duration"]

    cursor.execute(
        "INSERT INTO exams (title, description, duration) VALUES (%s,%s,%s)",
        (title, description, duration),
    )
    db.commit()

    return redirect("/admin-dashboard")


@app.route("/add-question")
def add_question():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template("add_questions.html")


@app.route("/save-question", methods=["POST"])
def save_question():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    exam_id = request.form["exam_id"]
    question = request.form["question"]
    option_a = request.form["option_a"]
    option_b = request.form["option_b"]
    option_c = request.form["option_c"]
    option_d = request.form["option_d"]
    correct_answer = request.form["correct_answer"]

    cursor.execute(
        """
        INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (exam_id, question, option_a, option_b, option_c, option_d, correct_answer),
    )
    db.commit()

    return redirect("/admin-dashboard")


@app.route("/start-exam/<int:exam_id>")
def start_exam(exam_id):
    redirect_response = require_student()
    if redirect_response:
        return redirect_response

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    local_cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = local_cursor.fetchall()

    local_cursor.execute("SELECT duration FROM exams WHERE id=%s", (exam_id,))
    exam = local_cursor.fetchone()
    local_cursor.close()
    local_db.close()

    if not exam:
        return "Exam not found"

    create_exam_activity(get_current_user_id(), exam_id)

    return render_template(
        "exam.html",
        questions=questions,
        exam_id=exam_id,
        exam_duration=exam[0],
        student_name=session.get("user_name", "Student"),
    )


@app.route("/exam-event", methods=["POST"])
def exam_event():
    redirect_response = require_student()
    if redirect_response:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    exam_id = request.form.get("exam_id")
    status = request.form.get("status")
    increment_warning = request.form.get("increment_warning") == "true"

    if not exam_id:
        return jsonify({"success": False, "message": "Missing exam_id"}), 400

    update_exam_activity(
        get_current_user_id(),
        exam_id,
        status=status,
        increment_warning=increment_warning,
    )
    return jsonify({"success": True})


@app.route("/submit-exam", methods=["POST"])
def submit_exam():
    redirect_response = require_student()
    if redirect_response:
        return redirect_response

    student_id = get_current_user_id()
    exam_id = request.form["exam_id"]
    final_status = request.form.get("final_status", "Submitted")

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    local_cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
    questions = local_cursor.fetchall()

    score = 0
    student_answers = {}

    for q in questions:
        qid = q[0]
        correct_answer = q[7]
        student_answer = request.form.get(f"q{qid}")

        student_answers[qid] = student_answer

        if student_answer == correct_answer:
            score += 1

    total_questions = len(questions)
    percentage = (score / total_questions) * 100 if total_questions > 0 else 0

    local_cursor.execute(
        """
        INSERT INTO results (student_id, exam_id, score, total_questions)
        VALUES (%s, %s, %s, %s)
        """,
        (student_id, exam_id, score, total_questions),
    )

    answer_sql = """
    INSERT INTO student_answers
    (student_id, exam_id, question_id, student_answer, correct_answer)
    VALUES (%s,%s,%s,%s,%s)
    """

    for q in questions:
        qid = q[0]
        correct_answer = q[7]
        student_answer = student_answers.get(qid)
        local_cursor.execute(
            answer_sql,
            (student_id, exam_id, qid, student_answer, correct_answer),
        )

    local_db.commit()
    local_cursor.close()
    local_db.close()
    update_exam_activity(student_id, exam_id, status=final_status)

    return render_template(
        "result.html",
        score=score,
        total=total_questions,
        percentage=percentage,
        questions=questions,
        student_answers=student_answers,
    )


@app.route("/exam-history")
def exam_history():
    redirect_response = require_student()
    if redirect_response:
        return redirect_response

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    local_cursor.execute(
        """
        SELECT exams.title, results.score, results.total_questions
        FROM results
        JOIN exams ON exams.id = results.exam_id
        WHERE results.student_id = %s
        ORDER BY results.id DESC
        """,
        (get_current_user_id(),),
    )
    history = local_cursor.fetchall()
    local_cursor.close()
    local_db.close()

    return render_template("exam_history.html", history=history)


@app.route("/leaderboard")
def leaderboard():
    redirect_response = require_student()
    if redirect_response:
        return redirect_response

    local_db = get_db_connection()
    local_cursor = local_db.cursor(buffered=True)
    local_cursor.execute(
        """
        SELECT users.name,
               results.score,
               results.total_questions,
               exams.title
        FROM results
        JOIN users ON users.id = results.student_id
        JOIN exams ON exams.id = results.exam_id
        ORDER BY (results.score / results.total_questions) DESC, results.score DESC
        LIMIT 10
        """
    )
    leaderboard_data = local_cursor.fetchall()
    local_cursor.close()
    local_db.close()

    return render_template("leaderboard.html", leaderboard=leaderboard_data)


@app.route("/admin-analytics")
def admin_analytics():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    cursor.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM exams")
    total_exams = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM results")
    total_attempts = cursor.fetchone()[0]

    cursor.execute(
        "SELECT AVG((score / total_questions) * 100) FROM results WHERE total_questions > 0"
    )
    avg_score = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT users.name, (results.score / results.total_questions * 100) AS percentage
        FROM results
        JOIN users ON users.id = results.student_id
        WHERE results.total_questions > 0
        ORDER BY percentage DESC
        LIMIT 1
        """
    )
    top_student = cursor.fetchone()

    cursor.execute(
        """
        SELECT users.name,
               COUNT(results.id) AS attempts,
               AVG((results.score / results.total_questions) * 100) AS average_percentage
        FROM users
        LEFT JOIN results ON results.student_id = users.id AND results.total_questions > 0
        WHERE users.role = 'student'
        GROUP BY users.id, users.name
        ORDER BY users.name
        """
    )
    student_breakdown = cursor.fetchall()

    return render_template(
        "admin_analytics.html",
        total_students=total_students,
        total_exams=total_exams,
        total_attempts=total_attempts,
        avg_score=avg_score,
        top_student=top_student,
        student_breakdown=student_breakdown,
    )


@app.route("/monitor-exams")
def monitor_exams():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    cursor.execute(
        """
        SELECT users.name, exams.title, exam_activity.status, exam_activity.warning_count
        FROM exam_activity
        JOIN users ON users.id = exam_activity.student_id
        JOIN exams ON exams.id = exam_activity.exam_id
        ORDER BY exam_activity.id DESC
        """
    )
    activity = cursor.fetchall()

    return render_template("monitor.html", activity=activity)


@app.route("/student_performance")
def student_performance():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    cursor.execute(
        """
        SELECT users.name,
               exams.title,
               results.score,
               results.total_questions
        FROM results
        JOIN users ON users.id = results.student_id
        JOIN exams ON exams.id = results.exam_id
        ORDER BY users.name
        """
    )
    performance = cursor.fetchall()

    return render_template("student_performance.html", performance=performance)


@app.route("/performance-chart")
def performance_chart():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    cursor.execute(
        """
        SELECT users.name,
               AVG((results.score / results.total_questions) * 100) AS percentage
        FROM results
        JOIN users ON users.id = results.student_id
        WHERE results.total_questions > 0
        GROUP BY users.id, users.name
        ORDER BY users.name
        """
    )
    data = cursor.fetchall()

    names = [row[0] for row in data]
    scores = [float(row[1]) for row in data]

    return render_template("performance_chart.html", names=names, scores=scores)


if __name__ == "__main__":
    app.run(debug=True)
