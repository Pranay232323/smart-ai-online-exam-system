import csv
import io
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
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

WARNING_LIMIT = 3


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def get_cursor(connection, dictionary=False):
    return connection.cursor(buffered=True, dictionary=dictionary)


def fetch_all(query, params=(), dictionary=False):
    connection = get_db_connection()
    cursor = get_cursor(connection, dictionary=dictionary)
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def fetch_one(query, params=(), dictionary=False):
    connection = get_db_connection()
    cursor = get_cursor(connection, dictionary=dictionary)
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def execute_write(query, params=()):
    connection = get_db_connection()
    cursor = get_cursor(connection)
    try:
        cursor.execute(query, params)
        connection.commit()
        return cursor.lastrowid
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


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


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not get_current_user_id():
                flash("Please log in to continue.", "error")
                return redirect("/")

            if get_current_user_role() not in allowed_roles:
                flash("You do not have permission to access that page.", "error")
                if get_current_user_role() == "admin":
                    return redirect("/admin-dashboard")
                return redirect("/dashboard")

            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def login_required(view):
    return role_required("student", "admin")(view)


def student_required(view):
    return role_required("student")(view)


def admin_required(view):
    return role_required("admin")(view)


def parse_datetime_local(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def format_datetime_local(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%Y-%m-%dT%H:%M")


app.jinja_env.filters["datetime_local"] = format_datetime_local


def exam_status_label(exam):
    now = datetime.now()
    start_time = exam.get("start_time")
    end_time = exam.get("end_time")

    if not exam.get("is_active", 1):
        return "Inactive"
    if start_time and now < start_time:
        return "Upcoming"
    if end_time and now > end_time:
        return "Closed"
    return "Live"


def exam_schedule_text(exam):
    parts = []
    if exam.get("start_time"):
        parts.append(f"Starts: {exam['start_time'].strftime('%d %b %Y, %I:%M %p')}")
    if exam.get("end_time"):
        parts.append(f"Ends: {exam['end_time'].strftime('%d %b %Y, %I:%M %p')}")
    if not parts:
        return "Available any time while active."
    return " | ".join(parts)


def annotate_exam(exam):
    status = exam_status_label(exam)
    exam["status_label"] = status
    exam["schedule_text"] = exam_schedule_text(exam)
    exam["question_count"] = exam.get("question_count", 0) or 0
    exam["can_start"] = status == "Live" and exam["question_count"] > 0
    return exam


def get_student_chatbot_context(student_id):
    context = {
        "student_id": student_id,
        "exam_count": 0,
        "exam_titles": [],
        "attempt_count": 0,
        "latest_result": None,
        "top_score_percentage": None,
    }

    exams = fetch_all(
        """
        SELECT id, title, description, duration, start_time, end_time, is_active, 0 AS question_count
        FROM exams
        ORDER BY id DESC
        """,
        dictionary=True,
    )
    exams = [annotate_exam(exam) for exam in exams]
    live_exams = [exam for exam in exams if exam["status_label"] == "Live"]
    context["exam_titles"] = [exam["title"] for exam in live_exams]
    context["exam_count"] = len(live_exams)

    context["latest_result"] = fetch_one(
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

    attempt_row = fetch_one(
        "SELECT COUNT(*) FROM results WHERE student_id = %s",
        (student_id,),
    )
    context["attempt_count"] = attempt_row[0] if attempt_row else 0

    top_score = fetch_one(
        """
        SELECT MAX((score / total_questions) * 100)
        FROM results
        WHERE student_id = %s AND total_questions > 0
        """,
        (student_id,),
    )
    context["top_score_percentage"] = (
        float(top_score[0]) if top_score and top_score[0] is not None else None
    )

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
            return "There are no live exams available right now."

        preview = ", ".join(context["exam_titles"][:3])
        if context["exam_count"] > 3:
            preview += ", and more"

        return (
            f"There are {context['exam_count']} live exams available right now. "
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
                "The Student Dashboard shows your live and upcoming exams. "
                "Use the Start Exam button beside a live exam when you are ready."
            ),
        ),
        (
            ["start exam", "begin exam", "take exam"],
            (
                "To start an exam, go to the Student Dashboard and click Start Exam "
                "next to a live exam. Upcoming or inactive exams cannot be opened yet."
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
                "The system may also auto-submit when time runs out or when repeated rule violations are detected."
            ),
        ),
        (
            ["tab", "switch tab", "cheat", "warning", "reload", "refresh"],
            (
                f"During an exam, tab switching, fullscreen exit, copy-paste, and reload are tracked. "
                f"After {WARNING_LIMIT} warnings the exam is auto-submitted."
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
            ["profile", "my profile"],
            "Open your profile page from the dashboard to see your summary statistics and weak areas.",
        ),
    ]

    for keywords, response in faq_responses:
        if any(keyword in text for keyword in keywords):
            return response

    return (
        "I can help with basic website questions. Try asking about starting an exam, "
        "exam timer, profile, exam history, leaderboard, results, or dashboard navigation."
    )


def create_exam_activity(student_id, exam_id):
    connection = get_db_connection()
    cursor = get_cursor(connection)
    try:
        cursor.execute(
            """
            INSERT INTO exam_activity (student_id, exam_id, status, warning_count, last_event)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (student_id, exam_id, "In Progress", 0, "Exam Started"),
        )
        connection.commit()
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def log_exam_event(
    student_id,
    exam_id,
    event_type,
    message=None,
    warning_delta=0,
    status=None,
):
    connection = get_db_connection()
    cursor = get_cursor(connection, dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, warning_count
            FROM exam_activity
            WHERE student_id = %s AND exam_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (student_id, exam_id),
        )
        activity = cursor.fetchone()
        if not activity:
            cursor.execute(
                """
                INSERT INTO exam_activity (student_id, exam_id, status, warning_count, last_event)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (student_id, exam_id, "In Progress", 0, "Exam Started"),
            )
            activity = {"id": cursor.lastrowid, "warning_count": 0}

        new_warning_count = activity["warning_count"] + warning_delta
        new_status = status or ("Warning Issued" if warning_delta else "In Progress")
        submitted_at = datetime.now() if "Submitted" in new_status else None

        cursor.execute(
            """
            UPDATE exam_activity
            SET status = %s, warning_count = %s, last_event = %s, submitted_at = %s
            WHERE id = %s
            """,
            (
                new_status,
                new_warning_count,
                message or event_type,
                submitted_at,
                activity["id"],
            ),
        )

        cursor.execute(
            """
            INSERT INTO exam_event_logs (student_id, exam_id, event_type, message, warning_count)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                student_id,
                exam_id,
                event_type,
                message or event_type,
                new_warning_count,
            ),
        )

        connection.commit()
        return new_warning_count
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def build_csv_response(filename, header, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def get_profile_data(student_id):
    user = fetch_one(
        "SELECT id, name, email, role FROM users WHERE id = %s",
        (student_id,),
        dictionary=True,
    )

    summary = fetch_one(
        """
        SELECT COUNT(*) AS total_exams,
               COALESCE(AVG((score / total_questions) * 100), 0) AS average_score,
               COALESCE(MAX((score / total_questions) * 100), 0) AS best_score
        FROM results
        WHERE student_id = %s AND total_questions > 0
        """,
        (student_id,),
        dictionary=True,
    )

    weak_areas = fetch_all(
        """
        SELECT exams.title,
               AVG((results.score / results.total_questions) * 100) AS percentage
        FROM results
        JOIN exams ON exams.id = results.exam_id
        WHERE results.student_id = %s AND results.total_questions > 0
        GROUP BY exams.id, exams.title
        ORDER BY percentage ASC
        LIMIT 3
        """,
        (student_id,),
        dictionary=True,
    )

    recent_results = fetch_all(
        """
        SELECT exams.title,
               results.score,
               results.total_questions,
               results.created_at
        FROM results
        JOIN exams ON exams.id = results.exam_id
        WHERE results.student_id = %s
        ORDER BY results.id DESC
        LIMIT 5
        """,
        (student_id,),
        dictionary=True,
    )

    return {
        "user": user,
        "summary": summary,
        "weak_areas": weak_areas,
        "recent_results": recent_results,
    }


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (DB_CONFIG["database"], table_name, column_name),
    )
    return cursor.fetchone()[0] > 0


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
        """,
        (DB_CONFIG["database"], table_name),
    )
    return cursor.fetchone()[0] > 0


def ensure_schema_updates():
    connection = get_db_connection()
    cursor = get_cursor(connection)
    try:
        if not column_exists(cursor, "exams", "start_time"):
            cursor.execute("ALTER TABLE exams ADD COLUMN start_time DATETIME NULL")
        if not column_exists(cursor, "exams", "end_time"):
            cursor.execute("ALTER TABLE exams ADD COLUMN end_time DATETIME NULL")
        if not column_exists(cursor, "exams", "is_active"):
            cursor.execute("ALTER TABLE exams ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1")

        if not column_exists(cursor, "exam_activity", "last_event"):
            cursor.execute("ALTER TABLE exam_activity ADD COLUMN last_event VARCHAR(255) NULL")
        if not column_exists(cursor, "exam_activity", "submitted_at"):
            cursor.execute("ALTER TABLE exam_activity ADD COLUMN submitted_at DATETIME NULL")
        if not column_exists(cursor, "exam_activity", "updated_at"):
            cursor.execute(
                """
                ALTER TABLE exam_activity
                ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
                """
            )

        if not table_exists(cursor, "exam_event_logs"):
            cursor.execute(
                """
                CREATE TABLE exam_event_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    exam_id INT NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    message VARCHAR(255) NOT NULL,
                    warning_count INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_event_logs_student
                        FOREIGN KEY (student_id) REFERENCES users(id)
                        ON DELETE CASCADE,
                    CONSTRAINT fk_event_logs_exam
                        FOREIGN KEY (exam_id) REFERENCES exams(id)
                        ON DELETE CASCADE
                )
                """
            )

        connection.commit()
    finally:
        cursor.close()
        connection.close()


@app.route("/")
def home():
    if get_current_user_id():
        if get_current_user_role() == "admin":
            return redirect("/admin-dashboard")
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/test-db")
def test_db():
    result = fetch_all("SELECT id, name, email, role FROM users")
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
    user = fetch_one("SELECT id, email FROM users WHERE email = %s", (email,))

    if not user:
        flash("No account was found with that email address.", "error")
        return render_template("forgot_password.html", form_data={"email": email})

    session["password_reset_email"] = user[1]
    flash("Email verified. Please set your new password.", "success")
    return redirect("/reset-password")


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

    execute_write(
        "UPDATE users SET password = %s WHERE email = %s",
        (generate_password_hash(password), reset_email),
    )

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

    existing_user = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    if existing_user:
        flash("An account with this email already exists.", "error")
        return render_template("register.html", form_data={"name": name, "email": email})

    execute_write(
        "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
        (name, email, generate_password_hash(password), "student"),
    )
    flash("Registration successful. Please log in.", "success")
    return redirect("/")


@app.route("/login-user", methods=["POST"])
def login_user():
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    connection = get_db_connection()
    cursor = get_cursor(connection)

    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            flash("Invalid email or password.", "error")
            return render_template("login.html", form_data={"email": email})

        password_is_valid, should_upgrade = verify_password(user[3], password)
        if not password_is_valid:
            flash("Invalid email or password.", "error")
            return render_template("login.html", form_data={"email": email})

        if should_upgrade:
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (generate_password_hash(password), user[0]),
            )
            connection.commit()

        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_email"] = user[2]
        session["user_role"] = user[4]

        if user[4] == "admin":
            return redirect("/admin-dashboard")
        return redirect("/dashboard")
    finally:
        cursor.close()
        connection.close()


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
@student_required
def dashboard():
    exams = fetch_all(
        """
        SELECT exams.id,
               exams.title,
               exams.description,
               exams.duration,
               exams.start_time,
               exams.end_time,
               exams.is_active,
               COUNT(questions.id) AS question_count
        FROM exams
        LEFT JOIN questions ON questions.exam_id = exams.id
        GROUP BY exams.id, exams.title, exams.description, exams.duration, exams.start_time, exams.end_time, exams.is_active
        ORDER BY exams.start_time IS NULL DESC, exams.start_time ASC, exams.id DESC
        """,
        dictionary=True,
    )
    exams = [annotate_exam(exam) for exam in exams]

    profile = get_profile_data(get_current_user_id())
    return render_template(
        "dashboard.html",
        exams=exams,
        student_name=session.get("user_name", "Student"),
        summary=profile["summary"],
    )


@app.route("/profile")
@student_required
def profile():
    profile_data = get_profile_data(get_current_user_id())
    return render_template("profile.html", **profile_data)


@app.route("/student-chatbot", methods=["POST"])
@student_required
def student_chatbot():
    message = request.form.get("message")
    if message is None and request.is_json:
        payload = request.get_json(silent=True) or {}
        message = payload.get("message", "")

    reply = generate_student_chatbot_reply(message, student_id=get_current_user_id())
    return jsonify({"reply": reply})


@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    stats = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM exams) AS total_exams,
            (SELECT COUNT(*) FROM users WHERE role = 'student') AS total_students,
            (SELECT COUNT(*) FROM results) AS total_attempts,
            (SELECT COUNT(*) FROM exam_event_logs) AS total_events
        """,
        dictionary=True,
    )
    recent_exams = fetch_all(
        """
        SELECT exams.id, exams.title, exams.duration, exams.start_time, exams.end_time, exams.is_active,
               COUNT(questions.id) AS question_count
        FROM exams
        LEFT JOIN questions ON questions.exam_id = exams.id
        GROUP BY exams.id, exams.title, exams.duration, exams.start_time, exams.end_time, exams.is_active
        ORDER BY exams.id DESC
        LIMIT 4
        """,
        dictionary=True,
    )
    recent_exams = [annotate_exam(exam) for exam in recent_exams]

    return render_template("admin_dashboard.html", stats=stats, recent_exams=recent_exams)


@app.route("/create-exam")
@admin_required
def create_exam():
    return render_template("create_exam.html")


@app.route("/save-exam", methods=["POST"])
@admin_required
def save_exam():
    title = request.form["title"].strip()
    description = request.form["description"].strip()
    duration = request.form["duration"]
    start_time = parse_datetime_local(request.form.get("start_time"))
    end_time = parse_datetime_local(request.form.get("end_time"))
    is_active = 1 if request.form.get("is_active") == "on" else 0

    if start_time and end_time and end_time <= start_time:
        flash("Exam end time must be after the start time.", "error")
        return render_template("create_exam.html")

    execute_write(
        """
        INSERT INTO exams (title, description, duration, start_time, end_time, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (title, description, duration, start_time, end_time, is_active),
    )
    flash("Exam created successfully.", "success")
    return redirect("/manage-exams")


@app.route("/manage-exams")
@admin_required
def manage_exams():
    exams = fetch_all(
        """
        SELECT exams.id,
               exams.title,
               exams.description,
               exams.duration,
               exams.start_time,
               exams.end_time,
               exams.is_active,
               COUNT(DISTINCT questions.id) AS question_count,
               COUNT(DISTINCT results.id) AS attempt_count
        FROM exams
        LEFT JOIN questions ON questions.exam_id = exams.id
        LEFT JOIN results ON results.exam_id = exams.id
        GROUP BY exams.id, exams.title, exams.description, exams.duration, exams.start_time, exams.end_time, exams.is_active
        ORDER BY exams.id DESC
        """,
        dictionary=True,
    )
    exams = [annotate_exam(exam) for exam in exams]
    return render_template("manage_exams.html", exams=exams)


@app.route("/edit-exam/<int:exam_id>")
@admin_required
def edit_exam(exam_id):
    exam = fetch_one(
        """
        SELECT id, title, description, duration, start_time, end_time, is_active
        FROM exams
        WHERE id = %s
        """,
        (exam_id,),
        dictionary=True,
    )
    if not exam:
        flash("Exam not found.", "error")
        return redirect("/manage-exams")
    return render_template("edit_exam.html", exam=exam)


@app.route("/update-exam/<int:exam_id>", methods=["POST"])
@admin_required
def update_exam(exam_id):
    title = request.form["title"].strip()
    description = request.form["description"].strip()
    duration = request.form["duration"]
    start_time = parse_datetime_local(request.form.get("start_time"))
    end_time = parse_datetime_local(request.form.get("end_time"))
    is_active = 1 if request.form.get("is_active") == "on" else 0

    if start_time and end_time and end_time <= start_time:
        flash("Exam end time must be after the start time.", "error")
        exam = {
            "id": exam_id,
            "title": title,
            "description": description,
            "duration": int(duration),
            "start_time": start_time,
            "end_time": end_time,
            "is_active": is_active,
        }
        return render_template("edit_exam.html", exam=exam)

    execute_write(
        """
        UPDATE exams
        SET title = %s,
            description = %s,
            duration = %s,
            start_time = %s,
            end_time = %s,
            is_active = %s
        WHERE id = %s
        """,
        (title, description, duration, start_time, end_time, is_active, exam_id),
    )
    flash("Exam updated successfully.", "success")
    return redirect("/manage-exams")


@app.route("/delete-exam/<int:exam_id>", methods=["POST"])
@admin_required
def delete_exam(exam_id):
    execute_write("DELETE FROM exams WHERE id = %s", (exam_id,))
    flash("Exam deleted successfully.", "success")
    return redirect("/manage-exams")


@app.route("/add-question")
@admin_required
def add_question():
    exams = fetch_all(
        "SELECT id, title FROM exams ORDER BY title",
        dictionary=True,
    )
    return render_template("add_questions.html", exams=exams)


@app.route("/manage-questions/<int:exam_id>")
@admin_required
def manage_questions(exam_id):
    exam = fetch_one(
        "SELECT id, title, description FROM exams WHERE id = %s",
        (exam_id,),
        dictionary=True,
    )
    if not exam:
        flash("Exam not found.", "error")
        return redirect("/manage-exams")

    questions = fetch_all(
        """
        SELECT id, question, option_a, option_b, option_c, option_d, correct_answer
        FROM questions
        WHERE exam_id = %s
        ORDER BY id ASC
        """,
        (exam_id,),
        dictionary=True,
    )
    return render_template("manage_questions.html", exam=exam, questions=questions)


@app.route("/save-question", methods=["POST"])
@admin_required
def save_question():
    exam_id = request.form["exam_id"]
    question = request.form["question"].strip()
    option_a = request.form["option_a"].strip()
    option_b = request.form["option_b"].strip()
    option_c = request.form["option_c"].strip()
    option_d = request.form["option_d"].strip()
    correct_answer = request.form["correct_answer"]

    execute_write(
        """
        INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (exam_id, question, option_a, option_b, option_c, option_d, correct_answer),
    )
    flash("Question saved successfully.", "success")

    if request.form.get("return_to") == "manage":
        return redirect(f"/manage-questions/{exam_id}")
    return redirect("/add-question")


@app.route("/edit-question/<int:question_id>")
@admin_required
def edit_question(question_id):
    question = fetch_one(
        """
        SELECT questions.id,
               questions.exam_id,
               questions.question,
               questions.option_a,
               questions.option_b,
               questions.option_c,
               questions.option_d,
               questions.correct_answer,
               exams.title AS exam_title
        FROM questions
        JOIN exams ON exams.id = questions.exam_id
        WHERE questions.id = %s
        """,
        (question_id,),
        dictionary=True,
    )
    if not question:
        flash("Question not found.", "error")
        return redirect("/manage-exams")
    return render_template("edit_question.html", question=question)


@app.route("/update-question/<int:question_id>", methods=["POST"])
@admin_required
def update_question(question_id):
    exam_id = request.form["exam_id"]
    execute_write(
        """
        UPDATE questions
        SET question = %s,
            option_a = %s,
            option_b = %s,
            option_c = %s,
            option_d = %s,
            correct_answer = %s
        WHERE id = %s
        """,
        (
            request.form["question"].strip(),
            request.form["option_a"].strip(),
            request.form["option_b"].strip(),
            request.form["option_c"].strip(),
            request.form["option_d"].strip(),
            request.form["correct_answer"],
            question_id,
        ),
    )
    flash("Question updated successfully.", "success")
    return redirect(f"/manage-questions/{exam_id}")


@app.route("/delete-question/<int:question_id>", methods=["POST"])
@admin_required
def delete_question(question_id):
    question = fetch_one(
        "SELECT exam_id FROM questions WHERE id = %s",
        (question_id,),
    )
    if not question:
        flash("Question not found.", "error")
        return redirect("/manage-exams")

    execute_write("DELETE FROM questions WHERE id = %s", (question_id,))
    flash("Question deleted successfully.", "success")
    return redirect(f"/manage-questions/{question[0]}")


@app.route("/start-exam/<int:exam_id>")
@student_required
def start_exam(exam_id):
    exam = fetch_one(
        """
        SELECT exams.id,
               exams.title,
               exams.description,
               exams.duration,
               exams.start_time,
               exams.end_time,
               exams.is_active,
               COUNT(questions.id) AS question_count
        FROM exams
        LEFT JOIN questions ON questions.exam_id = exams.id
        WHERE exams.id = %s
        GROUP BY exams.id, exams.title, exams.description, exams.duration, exams.start_time, exams.end_time, exams.is_active
        """,
        (exam_id,),
        dictionary=True,
    )
    if not exam:
        flash("Exam not found.", "error")
        return redirect("/dashboard")

    exam = annotate_exam(exam)
    if not exam["can_start"]:
        flash(f"This exam cannot be started right now. Status: {exam['status_label']}.", "error")
        return redirect("/dashboard")

    questions = fetch_all(
        """
        SELECT id, exam_id, question, option_a, option_b, option_c, option_d, correct_answer
        FROM questions
        WHERE exam_id = %s
        ORDER BY id ASC
        """,
        (exam_id,),
    )

    create_exam_activity(get_current_user_id(), exam_id)
    log_exam_event(get_current_user_id(), exam_id, "Exam Started", "Exam started by student")

    return render_template(
        "exam.html",
        questions=questions,
        exam=exam,
        exam_id=exam_id,
        exam_duration=exam["duration"],
        student_name=session.get("user_name", "Student"),
        warning_limit=WARNING_LIMIT,
    )


@app.route("/exam-event", methods=["POST"])
@student_required
def exam_event():
    exam_id = request.form.get("exam_id")
    event_type = request.form.get("event_type") or request.form.get("status") or "Activity"
    message = request.form.get("message") or event_type
    increment_warning = request.form.get("increment_warning") == "true"
    status = request.form.get("status")

    if not exam_id:
        return jsonify({"success": False, "message": "Missing exam_id"}), 400

    warning_count = log_exam_event(
        get_current_user_id(),
        exam_id,
        event_type=event_type,
        message=message,
        warning_delta=1 if increment_warning else 0,
        status=status,
    )

    should_auto_submit = warning_count >= WARNING_LIMIT
    if should_auto_submit and not status:
        log_exam_event(
            get_current_user_id(),
            exam_id,
            event_type="Warning Limit Reached",
            message="Warning limit reached; auto submission required",
            status="Auto Submitted",
        )

    return jsonify(
        {
            "success": True,
            "warning_count": warning_count,
            "warning_limit": WARNING_LIMIT,
            "should_auto_submit": should_auto_submit,
        }
    )


@app.route("/submit-exam", methods=["POST"])
@student_required
def submit_exam():
    student_id = get_current_user_id()
    exam_id = request.form["exam_id"]
    final_status = request.form.get("final_status", "Submitted")

    connection = get_db_connection()
    cursor = get_cursor(connection)
    try:
        cursor.execute(
            """
            SELECT id, exam_id, question, option_a, option_b, option_c, option_d, correct_answer
            FROM questions
            WHERE exam_id = %s
            ORDER BY id ASC
            """,
            (exam_id,),
        )
        questions = cursor.fetchall()

        score = 0
        student_answers = {}
        for question in questions:
            question_id = question[0]
            correct_answer = question[7]
            student_answer = request.form.get(f"q{question_id}")
            student_answers[question_id] = student_answer
            if student_answer == correct_answer:
                score += 1

        total_questions = len(questions)
        percentage = (score / total_questions) * 100 if total_questions > 0 else 0

        cursor.execute(
            """
            INSERT INTO results (student_id, exam_id, score, total_questions)
            VALUES (%s, %s, %s, %s)
            """,
            (student_id, exam_id, score, total_questions),
        )

        for question in questions:
            question_id = question[0]
            cursor.execute(
                """
                INSERT INTO student_answers
                (student_id, exam_id, question_id, student_answer, correct_answer)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    student_id,
                    exam_id,
                    question_id,
                    student_answers.get(question_id),
                    question[7],
                ),
            )

        connection.commit()
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    log_exam_event(
        student_id,
        exam_id,
        event_type=final_status,
        message=f"Exam finished with status: {final_status}",
        status=final_status,
    )

    return render_template(
        "result.html",
        score=score,
        total=total_questions,
        percentage=percentage,
        questions=questions,
        student_answers=student_answers,
        final_status=final_status,
    )


@app.route("/exam-history")
@student_required
def exam_history():
    history = fetch_all(
        """
        SELECT exams.title,
               results.score,
               results.total_questions,
               results.created_at
        FROM results
        JOIN exams ON exams.id = results.exam_id
        WHERE results.student_id = %s
        ORDER BY results.id DESC
        """,
        (get_current_user_id(),),
    )
    return render_template("exam_history.html", history=history)


@app.route("/leaderboard")
@student_required
def leaderboard():
    leaderboard_data = fetch_all(
        """
        SELECT users.name,
               results.score,
               results.total_questions,
               exams.title
        FROM results
        JOIN users ON users.id = results.student_id
        JOIN exams ON exams.id = results.exam_id
        WHERE results.total_questions > 0
        ORDER BY (results.score / results.total_questions) DESC, results.score DESC
        LIMIT 10
        """
    )
    return render_template("leaderboard.html", leaderboard=leaderboard_data)


@app.route("/admin-analytics")
@admin_required
def admin_analytics():
    total_students = fetch_one("SELECT COUNT(*) FROM users WHERE role='student'")[0]
    total_exams = fetch_one("SELECT COUNT(*) FROM exams")[0]
    total_attempts = fetch_one("SELECT COUNT(*) FROM results")[0]
    avg_score = fetch_one(
        "SELECT AVG((score / total_questions) * 100) FROM results WHERE total_questions > 0"
    )[0]
    top_student = fetch_one(
        """
        SELECT users.name, (results.score / results.total_questions * 100) AS percentage
        FROM results
        JOIN users ON users.id = results.student_id
        WHERE results.total_questions > 0
        ORDER BY percentage DESC
        LIMIT 1
        """
    )
    student_breakdown = fetch_all(
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
@admin_required
def monitor_exams():
    activity = fetch_all(
        """
        SELECT users.name,
               exams.title,
               exam_activity.status,
               exam_activity.warning_count,
               exam_activity.last_event,
               exam_activity.updated_at
        FROM exam_activity
        JOIN users ON users.id = exam_activity.student_id
        JOIN exams ON exams.id = exam_activity.exam_id
        ORDER BY exam_activity.id DESC
        """,
        dictionary=True,
    )
    event_logs = fetch_all(
        """
        SELECT users.name,
               exams.title,
               exam_event_logs.event_type,
               exam_event_logs.message,
               exam_event_logs.warning_count,
               exam_event_logs.created_at
        FROM exam_event_logs
        JOIN users ON users.id = exam_event_logs.student_id
        JOIN exams ON exams.id = exam_event_logs.exam_id
        ORDER BY exam_event_logs.id DESC
        LIMIT 100
        """,
        dictionary=True,
    )
    return render_template("monitor.html", activity=activity, event_logs=event_logs)


@app.route("/student_performance")
@admin_required
def student_performance():
    performance = fetch_all(
        """
        SELECT users.name,
               exams.title,
               results.score,
               results.total_questions
        FROM results
        JOIN users ON users.id = results.student_id
        JOIN exams ON exams.id = results.exam_id
        ORDER BY users.name, results.id DESC
        """
    )
    return render_template("student_performance.html", performance=performance)


@app.route("/performance-chart")
@admin_required
def performance_chart():
    data = fetch_all(
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
    names = [row[0] for row in data]
    scores = [float(row[1]) for row in data]
    return render_template("performance_chart.html", names=names, scores=scores)


@app.route("/export/results")
@admin_required
def export_results():
    rows = fetch_all(
        """
        SELECT users.name,
               users.email,
               exams.title,
               results.score,
               results.total_questions,
               ROUND((results.score / results.total_questions) * 100, 2) AS percentage,
               results.created_at
        FROM results
        JOIN users ON users.id = results.student_id
        JOIN exams ON exams.id = results.exam_id
        WHERE results.total_questions > 0
        ORDER BY results.created_at DESC
        """
    )
    return build_csv_response(
        "results_report.csv",
        ["Student", "Email", "Exam", "Score", "Total", "Percentage", "Submitted At"],
        rows,
    )


@app.route("/export/analytics")
@admin_required
def export_analytics():
    rows = fetch_all(
        """
        SELECT users.name,
               users.email,
               COUNT(results.id) AS attempts,
               ROUND(AVG((results.score / results.total_questions) * 100), 2) AS average_percentage,
               ROUND(MAX((results.score / results.total_questions) * 100), 2) AS best_percentage
        FROM users
        LEFT JOIN results
            ON results.student_id = users.id
           AND results.total_questions > 0
        WHERE users.role = 'student'
        GROUP BY users.id, users.name, users.email
        ORDER BY users.name
        """
    )
    return build_csv_response(
        "analytics_report.csv",
        ["Student", "Email", "Attempts", "Average Percentage", "Best Percentage"],
        rows,
    )


@app.route("/export/monitoring")
@admin_required
def export_monitoring():
    rows = fetch_all(
        """
        SELECT users.name,
               exams.title,
               exam_event_logs.event_type,
               exam_event_logs.message,
               exam_event_logs.warning_count,
               exam_event_logs.created_at
        FROM exam_event_logs
        JOIN users ON users.id = exam_event_logs.student_id
        JOIN exams ON exams.id = exam_event_logs.exam_id
        ORDER BY exam_event_logs.created_at DESC
        """
    )
    return build_csv_response(
        "monitoring_report.csv",
        ["Student", "Exam", "Event Type", "Message", "Warnings", "Created At"],
        rows,
    )


ensure_schema_updates()


if __name__ == "__main__":
    app.run(debug=True)
