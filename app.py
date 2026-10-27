import os
import re
import csv
import io
import random
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, make_response, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)

# Session and cookie security
app.secret_key = os.environ.get("SECRET_KEY", "quizzy-pro-secret-session-key-v2-secure")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

DB = os.path.join(BASE_DIR, "quizzy.db")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            mobile TEXT UNIQUE,
            mobile_verified INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'General',
            difficulty TEXT DEFAULT 'Medium',
            duration INTEGER NOT NULL DEFAULT 10,
            published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            a TEXT NOT NULL,
            b TEXT NOT NULL,
            c TEXT NOT NULL,
            d TEXT NOT NULL,
            correct TEXT NOT NULL,
            explanation TEXT DEFAULT '',
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quiz_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            time_taken_seconds INTEGER DEFAULT 0,
            taken_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attempt_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            selected_option TEXT,
            is_correct INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS helpdesk_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            admin_reply TEXT,
            created_at TEXT NOT NULL,
            replied_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        """)

        # Safely migrate older database schemas if columns are missing
        user_cols = [r["name"] for r in con.execute("PRAGMA table_info(users)").fetchall()]
        if "mobile" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN mobile TEXT")
        if "mobile_verified" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN mobile_verified INTEGER NOT NULL DEFAULT 1")
        if "created_at" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")

        quiz_cols = [r["name"] for r in con.execute("PRAGMA table_info(quizzes)").fetchall()]
        if "category" not in quiz_cols:
            con.execute("ALTER TABLE quizzes ADD COLUMN category TEXT DEFAULT 'General'")
        if "difficulty" not in quiz_cols:
            con.execute("ALTER TABLE quizzes ADD COLUMN difficulty TEXT DEFAULT 'Medium'")
        if "created_at" not in quiz_cols:
            con.execute("ALTER TABLE quizzes ADD COLUMN created_at TEXT DEFAULT ''")

        question_cols = [r["name"] for r in con.execute("PRAGMA table_info(questions)").fetchall()]
        if "explanation" not in question_cols:
            con.execute("ALTER TABLE questions ADD COLUMN explanation TEXT DEFAULT ''")

        attempt_cols = [r["name"] for r in con.execute("PRAGMA table_info(attempts)").fetchall()]
        if "time_taken_seconds" not in attempt_cols:
            con.execute("ALTER TABLE attempts ADD COLUMN time_taken_seconds INTEGER DEFAULT 0")

        # Seed admin account if missing
        if not con.execute("SELECT id FROM users WHERE email=?", ("admin@quizzy.com",)).fetchone():
            con.execute(
                "INSERT INTO users(name, email, password, role, mobile_verified) VALUES(?,?,?,?,1)",
                ("Quizzy Admin", "admin@quizzy.com", generate_password_hash("Admin@123"), "admin")
            )

        # Seed primary demo student account
        if not con.execute("SELECT id FROM users WHERE email=?", ("student@quizzy.com",)).fetchone():
            con.execute(
                "INSERT INTO users(name, email, mobile, password, role, mobile_verified) VALUES(?,?,?,?,?,1)",
                ("Demo Student", "student@quizzy.com", "9876543210", generate_password_hash("Student@123"), "student")
            )

        # Seed additional students for realistic attendance & leaderboard
        extra_students = [
            ("Rahul Sharma", "rahul.sharma@gmail.com", "9823011223"),
            ("Priya Patil", "priya.patil@gmail.com", "9823022334"),
            ("Rohit Deshmukh", "rohit.deshmukh@gmail.com", "9823033445"),
            ("Sneha Kulkarni", "sneha.kulkarni@gmail.com", "9823044556"),
            ("Aarav Mehta", "aarav.mehta@gmail.com", "9823055667")
        ]
        for s_name, s_email, s_mobile in extra_students:
            if not con.execute("SELECT id FROM users WHERE email=?", (s_email,)).fetchone():
                con.execute(
                    "INSERT INTO users(name, email, mobile, password, role, mobile_verified) VALUES(?,?,?,?,?,1)",
                    (s_name, s_email, s_mobile, generate_password_hash("Student@123"), "student")
                )

        # Ensure all core sample quizzes exist
        sample_quizzes = [
                {
                    "title": "Python Programming Essentials",
                    "description": "Test core Python syntax, built-in functions, data structures, and OOP basics.",
                    "category": "Programming",
                    "difficulty": "Easy",
                    "duration": 5,
                    "questions": [
                        ("Which keyword defines a function in Python?", "func", "def", "function", "define", "b",
                         "In Python, the 'def' keyword is used to declare and define a function."),
                        ("What is the output of len('quiz')?", "3", "4", "5", "Error", "b",
                         "The string 'quiz' contains exactly 4 characters."),
                        ("Which data type is immutable in Python?", "List", "Dictionary", "Set", "Tuple", "d",
                         "Tuples cannot be modified after creation, making them immutable."),
                        ("How do you start a single-line comment in Python?", "//", "#", "<!--", "**", "b",
                         "Python uses the hash '#' character for single-line comments."),
                        ("Which built-in function displays output on the console?", "echo()", "print()", "show()", "write()", "b",
                         "The print() function sends textual data to the standard console output.")
                    ]
                },
                {
                    "title": "Web Development & JavaScript",
                    "description": "Assess your understanding of modern HTML5, CSS layout principles, and core JS logic.",
                    "category": "Web Dev",
                    "difficulty": "Medium",
                    "duration": 8,
                    "questions": [
                        ("Which HTML tag is used to link an external CSS stylesheet?", "<script>", "<link>", "<style>", "<css>", "b",
                         "The <link rel='stylesheet' href='...'> tag connects external CSS files to HTML."),
                        ("In CSS Flexbox, which property aligns items along the cross axis?", "justify-content", "align-items", "flex-direction", "align-content", "b",
                         "'align-items' controls alignment along the cross axis, while 'justify-content' aligns on the main axis."),
                        ("Which JavaScript keyword declares a block-scoped variable that can be reassigned?", "const", "var", "let", "static", "c",
                         "'let' provides block-level scoping and allows variable values to be updated."),
                        ("What does JSON stand for?", "Java Source Object Network", "JavaScript Object Notation", "Joined System Output Node", "JavaScript Online Notebook", "b",
                         "JSON stands for JavaScript Object Notation, a lightweight data interchange format."),
                        ("Which event triggers when a user clicks an HTML element?", "onhover", "onchange", "onclick", "onsubmit", "c",
                         "The 'click' event triggers whenever a mouse click or tap occurs on an element.")
                    ]
                },
                {
                    "title": "General Science & Modern Tech",
                    "description": "Fun and insightful questions spanning physics, space exploration, and computer science history.",
                    "category": "Science & Tech",
                    "difficulty": "Easy",
                    "duration": 6,
                    "questions": [
                        ("What is the primary unit of electrical resistance?", "Volt", "Ampere", "Ohm", "Watt", "c",
                         "Electrical resistance is measured in Ohms (symbol: Ω), named after Georg Ohm."),
                        ("Which planet in our solar system is known as the Red Planet?", "Venus", "Mars", "Jupiter", "Saturn", "b",
                         "Mars appears reddish due to iron oxide (rust) widespread on its surface."),
                        ("Who is widely regarded as the first computer programmer?", "Alan Turing", "Ada Lovelace", "Charles Babbage", "Grace Hopper", "b",
                         "Ada Lovelace wrote the first algorithm intended for Charles Babbage's Analytical Engine."),
                        ("What gas do green plants absorb from the atmosphere during photosynthesis?", "Oxygen", "Carbon Dioxide", "Nitrogen", "Hydrogen", "b",
                         "Plants absorb Carbon Dioxide (CO2) and release Oxygen (O2) through photosynthesis."),
                        ("What does CPU stand for?", "Central Processing Unit", "Computer Program Utility", "Core Power Unit", "Central Peripheral Unit", "a",
                         "CPU stands for Central Processing Unit, the primary computational brain of a computer.")
                    ]
                },
                {
                    "title": "Artificial Intelligence & Data Science",
                    "description": "Explore fundamentals of Machine Learning, neural networks, and modern data processing.",
                    "category": "AI & Data",
                    "difficulty": "Hard",
                    "duration": 7,
                    "questions": [
                        ("In Machine Learning, what type of learning uses labeled input-output pairs?", "Unsupervised Learning", "Supervised Learning", "Reinforcement Learning", "Self-Directed Learning", "b",
                         "Supervised learning trains models on labeled ground truth data."),
                        ("Which metric evaluates classification models by balancing precision and recall?", "MSE", "F1 Score", "R-squared", "Cosine Similarity", "b",
                         "The F1 score is the harmonic mean of precision and recall."),
                        ("What does the 'G' stand for in GPT language models?", "Generalized", "Generative", "Graphical", "Geometric", "b",
                         "GPT stands for Generative Pre-trained Transformer."),
                        ("Which Python library is the standard for numerical array calculations?", "Matplotlib", "NumPy", "Requests", "Flask", "b",
                         "NumPy provides high-performance multidimensional array objects and math operations."),
                        ("What is the primary purpose of cross-validation in Machine Learning?", "Speed up training", "Prevent overfitting and assess generalizability", "Increase dataset size", "Encrypt data", "b",
                         "Cross-validation tests model performance on unseen subsets to ensure it generalizes well.")
                    ]
                }
            ]

        for q_data in sample_quizzes:
            # Check if quiz with this title exists
            existing = con.execute("SELECT id FROM quizzes WHERE title=?", (q_data["title"],)).fetchone()
            if not existing:
                cur = con.execute(
                    "INSERT INTO quizzes(title, description, category, difficulty, duration, published) VALUES(?,?,?,?,?,1)",
                    (q_data["title"], q_data["description"], q_data["category"], q_data["difficulty"], q_data["duration"])
                )
                qid = cur.lastrowid
                qs = [
                    (qid, item[0], item[1], item[2], item[3], item[4], item[5], item[6])
                    for item in q_data["questions"]
                ]
                con.executemany(
                    "INSERT INTO questions(quiz_id, question, a, b, c, d, correct, explanation) VALUES(?,?,?,?,?,?,?,?)",
                    qs
                )

        # Pre-seed realistic attempts so students see active attendee counts & leaderboard
        attempt_count = con.execute("SELECT COUNT(*) AS c FROM attempts").fetchone()["c"]
        if attempt_count < 10:
            student_users = con.execute("SELECT id FROM users WHERE role='student'").fetchall()
            all_quizzes = con.execute("SELECT id FROM quizzes").fetchall()
            
            if student_users and all_quizzes:
                timestamps = [
                    "2026-10-15 10:30", "2026-10-15 14:15", "2026-10-16 09:20",
                    "2026-10-16 16:45", "2026-10-16 18:30", "2026-10-17 11:10",
                    "2026-10-17 12:40", "2026-10-17 14:05", "2026-10-17 15:50"
                ]
                for idx, q in enumerate(all_quizzes):
                    qid = q["id"]
                    q_questions = con.execute("SELECT * FROM questions WHERE quiz_id=?", (qid,)).fetchall()
                    total_q = len(q_questions) or 5
                    for s_idx, u in enumerate(student_users):
                        # Generate varying scores
                        score = max(2, min(total_q, (idx + s_idx) % (total_q + 1)))
                        ts = timestamps[(idx + s_idx) % len(timestamps)]
                        con.execute("""
                            INSERT INTO attempts(user_id, quiz_id, score, total, time_taken_seconds, taken_at)
                            VALUES(?, ?, ?, ?, ?, ?)
                        """, (u["id"], qid, score, total_q, random.randint(90, 280), ts))

        # Seed sample helpdesk tickets if empty
        ticket_count = con.execute("SELECT COUNT(*) AS c FROM helpdesk_tickets").fetchone()["c"]
        if ticket_count == 0:
            con.execute("""
                INSERT INTO helpdesk_tickets(user_id, name, email, category, subject, message, status, admin_reply, created_at, replied_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                2, "Demo Student", "student@quizzy.com", "Quiz Issue",
                "Clarification on Python Tuple immutability",
                "Hello, I had a question regarding question 3 in Python Essentials. Can tuples contain mutable items like lists?",
                "Resolved",
                "Hi Demo Student! Yes, a tuple itself is immutable, but if it contains a reference to a mutable object (such as a list), the contents of that list can still be mutated.",
                "2026-10-16 10:15", "2026-10-16 11:30"
            ))
            con.execute("""
                INSERT INTO helpdesk_tickets(user_id, name, email, category, subject, message, status, admin_reply, created_at, replied_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                3, "Rahul Sharma", "rahul.sharma@gmail.com", "Feature Suggestion",
                "Request to add React & TypeScript Quizzes",
                "Hi team! Really enjoying Quizzy Pro. Could you please add frontend tests for React Hooks and TypeScript?",
                "Open",
                None,
                "2026-10-17 09:45", None
            ))


@app.context_processor
def inject_globals():
    user = session.get("user")
    open_tickets = 0
    if user and user.get("role") == "admin":
        try:
            with db() as con:
                row = con.execute("SELECT COUNT(*) AS c FROM helpdesk_tickets WHERE status='Open'").fetchone()
                if row:
                    open_tickets = row["c"]
        except Exception:
            open_tickets = 0
    return {
        "current_user": user,
        "admin_open_tickets": open_tickets
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            flash("Please sign in as a student to access this page.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = session.get("user")
        if not user or user.get("role") != "admin":
            flash("Administrator login required. Please sign in through the Admin Portal.", "danger")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


# ==============================================================================
# Public & Home Routes
# ==============================================================================
@app.route("/")
def index():
    selected_cat = request.args.get("category", "").strip()
    search_q = request.args.get("q", "").strip()

    with db() as con:
        # Retrieve quizzes with dynamic student attendance and attempt counts
        query = """
            SELECT q.*,
                   COUNT(DISTINCT questions.id) AS question_count,
                   COUNT(DISTINCT attempts.id) AS attempt_count,
                   COUNT(DISTINCT attempts.user_id) AS student_count
            FROM quizzes q
            LEFT JOIN questions ON q.id = questions.quiz_id
            LEFT JOIN attempts ON q.id = attempts.quiz_id
            WHERE q.published = 1
        """
        params = []
        if selected_cat and selected_cat != "All":
            query += " AND q.category = ?"
            params.append(selected_cat)
        if search_q:
            query += " AND (q.title LIKE ? OR q.description LIKE ?)"
            params.extend([f"%{search_q}%", f"%{search_q}%"])

        query += " GROUP BY q.id ORDER BY q.id DESC"
        quizzes = con.execute(query, params).fetchall()

        # Categories list for filter pills
        cats = [r["category"] for r in con.execute("SELECT DISTINCT category FROM quizzes WHERE published=1 AND category IS NOT NULL").fetchall()]

        # Overall platform statistics for hero counter
        total_students = con.execute("SELECT COUNT(*) AS c FROM users WHERE role='student'").fetchone()["c"]
        total_attempts = con.execute("SELECT COUNT(*) AS c FROM attempts").fetchone()["c"]
        total_quizzes = con.execute("SELECT COUNT(*) AS c FROM quizzes WHERE published=1").fetchone()["c"]

        # Hall of fame leaderboard
        leaders = con.execute("""
            SELECT users.name, MAX(attempts.score) AS best, attempts.total,
                   COUNT(attempts.id) as tests_taken
            FROM attempts
            JOIN users ON users.id = attempts.user_id
            GROUP BY users.id
            ORDER BY best DESC, tests_taken DESC
            LIMIT 5
        """).fetchall()

    return render_template(
        "index.html",
        quizzes=quizzes,
        categories=cats,
        selected_category=selected_cat,
        search_query=search_q,
        leaders=leaders,
        platform_stats={
            "students": total_students,
            "attempts": total_attempts,
            "quizzes": total_quizzes
        }
    )


# ==============================================================================
# Separate Authentication (Student Login vs Admin Login)
# ==============================================================================

# 1. Student Login (Dedicated Student Portal)
@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, redirect accordingly
    if session.get("user"):
        if session["user"].get("role") == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("index"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")

        with db() as con:
            user = con.execute("""
                SELECT * FROM users
                WHERE lower(email)=? OR mobile=?
                LIMIT 1
            """, (identifier, identifier)).fetchone()

        if user and check_password_hash(user["password"], password):
            # Check if this is an admin account logging in via student page
            if user["role"] == "admin":
                session["user"] = {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "mobile": user["mobile"],
                    "role": user["role"]
                }
                flash(f"Administrator {user['name']} recognized. Redirected to Admin Dashboard.", "info")
                return redirect(url_for("admin"))

            session["user"] = {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "mobile": user["mobile"],
                "role": user["role"]
            }
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("index"))

        flash("Invalid student email / mobile number or password.", "danger")

    return render_template("login.html")


# 2. Admin Login (Dedicated Admin Portal)
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    # If already logged in as admin, go straight to admin dashboard
    if session.get("user") and session["user"].get("role") == "admin":
        return redirect(url_for("admin"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with db() as con:
            user = con.execute("SELECT * FROM users WHERE lower(email)=? LIMIT 1", (email,)).fetchone()

        if user and check_password_hash(user["password"], password):
            if user["role"] != "admin":
                flash("Access Denied: This account does not have administrator privileges. Please use the Student Login.", "danger")
                return render_template("admin_login.html")

            session["user"] = {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "mobile": user["mobile"],
                "role": user["role"]
            }
            flash(f"Admin authentication successful. Welcome, {user['name']}!", "success")
            return redirect(url_for("admin"))

        flash("Invalid administrator credentials or access restricted.", "danger")

    return render_template("admin_login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user"):
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")

        if not name or len(password) < 6 or (not email and not mobile):
            flash("Please enter your name, an email or mobile number, and a password (min 6 characters).", "danger")
            return render_template("register.html")

        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Please provide a valid email address.", "danger")
            return render_template("register.html")

        if mobile:
            if not re.fullmatch(r"[6-9]\d{9}", mobile):
                flash("Enter a valid 10-digit Indian mobile number (starting with 6, 7, 8, or 9).", "danger")
                return render_template("register.html")
        else:
            mobile = None

        stored_email = email or f"mobile_{mobile}@quizzy.local"

        try:
            with db() as con:
                con.execute("""
                    INSERT INTO users (name, email, mobile, password, role, mobile_verified)
                    VALUES(?, ?, ?, ?, 'student', 1)
                """, (name, stored_email, mobile, generate_password_hash(password)))
            flash("Student account created successfully! You can now log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email address or mobile number is already registered.", "danger")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("index"))


# ==============================================================================
# Quiz Taking, Student Attendance Stats, & Results Review
# ==============================================================================
@app.route("/quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    with db() as con:
        quiz = con.execute("SELECT * FROM quizzes WHERE id=? AND published=1", (quiz_id,)).fetchone()
        questions = con.execute("SELECT * FROM questions WHERE quiz_id=?", (quiz_id,)).fetchall()

        # Calculate attendee statistics for student: How many students have attended this quiz?
        attendee_stats = con.execute("""
            SELECT COUNT(DISTINCT user_id) AS student_count,
                   COUNT(id) AS attempt_count,
                   AVG(score) AS avg_score
            FROM attempts
            WHERE quiz_id=?
        """, (quiz_id,)).fetchone()

    if not quiz or not questions:
        flash("Quiz not found or contains no published questions.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        score = 0
        detailed_review = []
        user_id = session["user"]["id"]
        total = len(questions)
        time_taken = int(request.form.get("time_taken", "0") or 0)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        with db() as con:
            cur = con.execute("""
                INSERT INTO attempts (user_id, quiz_id, score, total, time_taken_seconds, taken_at)
                VALUES(?, ?, ?, ?, ?, ?)
            """, (user_id, quiz_id, 0, total, time_taken, timestamp))
            attempt_id = cur.lastrowid

            for q in questions:
                user_choice = request.form.get(str(q["id"]))
                is_correct = 1 if (user_choice and user_choice.strip().lower() == q["correct"].strip().lower()) else 0
                if is_correct:
                    score += 1

                con.execute("""
                    INSERT INTO attempt_answers(attempt_id, question_id, selected_option, is_correct)
                    VALUES(?, ?, ?, ?)
                """, (attempt_id, q["id"], user_choice, is_correct))

                detailed_review.append({
                    "id": q["id"],
                    "question": q["question"],
                    "a": q["a"], "b": q["b"], "c": q["c"], "d": q["d"],
                    "correct": q["correct"],
                    "user_choice": user_choice,
                    "is_correct": bool(is_correct),
                    "explanation": q["explanation"]
                })

            # Update final score for attempt
            con.execute("UPDATE attempts SET score=? WHERE id=?", (score, attempt_id))

        return render_template(
            "result.html",
            quiz=quiz,
            score=score,
            total=total,
            attempt_id=attempt_id,
            detailed_review=detailed_review,
            time_taken=time_taken,
            total_attendees=(attendee_stats["student_count"] or 0) + 1
        )

    qs = [dict(q) for q in questions]
    random.shuffle(qs)
    return render_template(
        "quiz.html",
        quiz=quiz,
        questions=qs,
        attendee_stats=attendee_stats
    )


@app.route("/review/<int:attempt_id>")
@login_required
def review_attempt(attempt_id):
    with db() as con:
        attempt = con.execute("""
            SELECT a.*, q.title as quiz_title, q.description as quiz_desc
            FROM attempts a
            JOIN quizzes q ON q.id = a.quiz_id
            WHERE a.id = ?
        """, (attempt_id,)).fetchone()

        if not attempt:
            flash("Attempt not found.", "warning")
            return redirect(url_for("history"))

        # Security check: student can only view their own attempts unless admin
        if session["user"]["role"] != "admin" and attempt["user_id"] != session["user"]["id"]:
            flash("Access denied to this quiz result.", "danger")
            return redirect(url_for("history"))

        # Fetch answers stored or questions fallback
        answers = con.execute("""
            SELECT q.id, q.question, q.a, q.b, q.c, q.d, q.correct, q.explanation,
                   aa.selected_option, aa.is_correct
            FROM questions q
            LEFT JOIN attempt_answers aa ON aa.question_id = q.id AND aa.attempt_id = ?
            WHERE q.quiz_id = ?
            ORDER BY q.id ASC
        """, (attempt_id, attempt["quiz_id"])).fetchall()

    return render_template("review.html", attempt=attempt, answers=answers)


@app.route("/history")
@login_required
def history():
    with db() as con:
        attempts = con.execute("""
            SELECT attempts.*, quizzes.title, quizzes.category
            FROM attempts
            JOIN quizzes ON quizzes.id = attempts.quiz_id
            WHERE attempts.user_id = ?
            ORDER BY attempts.id DESC
        """, (session["user"]["id"],)).fetchall()

    return render_template("history.html", attempts=attempts)


# ==============================================================================
# Helpdesk (Support Ticket System for Students & Admin)
# ==============================================================================
@app.route("/helpdesk", methods=["GET", "POST"])
def helpdesk():
    user = session.get("user")

    if request.method == "POST":
        name = request.form.get("name", "").strip() or (user["name"] if user else "")
        email = request.form.get("email", "").strip() or (user["email"] if user else "")
        category = request.form.get("category", "General").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        user_id = user["id"] if user else None

        if not name or not email or not subject or not message:
            flash("Please complete all required fields (Name, Email, Subject, and Message).", "danger")
        else:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            with db() as con:
                con.execute("""
                    INSERT INTO helpdesk_tickets(user_id, name, email, category, subject, message, status, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, 'Open', ?)
                """, (user_id, name, email, category, subject, message, now_str))
            flash("Your support ticket has been submitted! Our team will respond shortly.", "success")
            return redirect(url_for("helpdesk"))

    # If logged in, fetch user's past tickets
    my_tickets = []
    if user:
        with db() as con:
            my_tickets = con.execute("""
                SELECT * FROM helpdesk_tickets
                WHERE user_id = ? OR email = ?
                ORDER BY id DESC
            """, (user["id"], user["email"])).fetchall()

    return render_template("helpdesk.html", my_tickets=my_tickets)


@app.route("/admin/helpdesk")
@admin_required
def admin_helpdesk():
    status_filter = request.args.get("status", "").strip()

    with db() as con:
        query = "SELECT * FROM helpdesk_tickets"
        params = []
        if status_filter in ("Open", "Resolved", "In Progress"):
            query += " WHERE status = ?"
            params.append(status_filter)
        query += " ORDER BY id DESC"

        tickets = con.execute(query, params).fetchall()

        # Metrics
        open_count = con.execute("SELECT COUNT(*) AS c FROM helpdesk_tickets WHERE status='Open'").fetchone()["c"]
        resolved_count = con.execute("SELECT COUNT(*) AS c FROM helpdesk_tickets WHERE status='Resolved'").fetchone()["c"]
        total_count = con.execute("SELECT COUNT(*) AS c FROM helpdesk_tickets").fetchone()["c"]

    return render_template(
        "admin_helpdesk.html",
        tickets=tickets,
        open_count=open_count,
        resolved_count=resolved_count,
        total_count=total_count,
        current_filter=status_filter
    )


@app.route("/admin/helpdesk/<int:ticket_id>/reply", methods=["POST"])
@admin_required
def reply_ticket(ticket_id):
    reply_text = request.form.get("reply", "").strip()
    new_status = request.form.get("status", "Resolved").strip()

    if reply_text:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with db() as con:
            con.execute("""
                UPDATE helpdesk_tickets
                SET admin_reply = ?, status = ?, replied_at = ?
                WHERE id = ?
            """, (reply_text, new_status, now_str, ticket_id))
        flash("Response recorded and ticket updated.", "success")
    else:
        flash("Reply message cannot be empty.", "warning")

    return redirect(url_for("admin_helpdesk"))


@app.route("/admin/helpdesk/<int:ticket_id>/delete", methods=["POST"])
@admin_required
def delete_ticket(ticket_id):
    with db() as con:
        con.execute("DELETE FROM helpdesk_tickets WHERE id=?", (ticket_id,))
    flash("Ticket deleted successfully.", "info")
    return redirect(url_for("admin_helpdesk"))


# ==============================================================================
# Admin Control Center (Quizzes, Questions, Results, Export)
# ==============================================================================
@app.route("/admin")
@admin_required
def admin():
    search_query = request.args.get("q", "").strip()

    with db() as con:
        # Retrieve quizzes with question counts, attendee counts, and attempt counts
        quizzes = con.execute("""
            SELECT q.*,
                   COUNT(DISTINCT questions.id) AS question_count,
                   COUNT(DISTINCT attempts.id) AS attempt_count,
                   COUNT(DISTINCT attempts.user_id) AS student_count
            FROM quizzes q
            LEFT JOIN questions ON q.id = questions.quiz_id
            LEFT JOIN attempts ON q.id = attempts.quiz_id
            GROUP BY q.id
            ORDER BY q.id DESC
        """).fetchall()

        stats = con.execute("SELECT COUNT(*) AS users FROM users WHERE role='student'").fetchone()
        total_attempts = con.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"]

        # Student results query with optional search
        res_query = """
            SELECT attempts.id, attempts.user_id, users.name AS student_name, users.email,
                   quizzes.title AS quiz_title, attempts.score, attempts.total, attempts.taken_at
            FROM attempts
            JOIN users ON users.id = attempts.user_id
            JOIN quizzes ON quizzes.id = attempts.quiz_id
        """
        params = []
        if search_query:
            res_query += " WHERE users.name LIKE ? OR users.email LIKE ? OR quizzes.title LIKE ?"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        res_query += " ORDER BY attempts.id DESC LIMIT 100"

        results = con.execute(res_query, params).fetchall()

    return render_template(
        "admin.html",
        quizzes=quizzes,
        student_count=stats["users"],
        attempt_count=total_attempts,
        results=results,
        search_query=search_query
    )


@app.route("/admin/results")
@admin_required
def admin_results():
    with db() as con:
        results = con.execute("""
            SELECT attempts.id, attempts.user_id, users.name AS student_name, users.email,
                   quizzes.title AS quiz_title, attempts.score, attempts.total, attempts.taken_at
            FROM attempts
            JOIN users ON users.id = attempts.user_id
            JOIN quizzes ON quizzes.id = attempts.quiz_id
            ORDER BY attempts.id DESC
        """).fetchall()

    return render_template(
        "admin.html",
        quizzes=[],
        student_count=0,
        attempt_count=len(results),
        results=results,
        results_only=True
    )


@app.route("/admin/export/results")
@admin_required
def export_results_csv():
    with db() as con:
        rows = con.execute("""
            SELECT attempts.id AS attempt_id, users.name AS student_name, users.email AS student_email,
                   quizzes.title AS quiz_title, quizzes.category, attempts.score, attempts.total,
                   ROUND((attempts.score * 100.0 / attempts.total), 1) AS percentage,
                   attempts.taken_at
            FROM attempts
            JOIN users ON users.id = attempts.user_id
            JOIN quizzes ON quizzes.id = attempts.quiz_id
            ORDER BY attempts.id DESC
        """).fetchall()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Attempt ID", "Student Name", "Email", "Quiz Title", "Category", "Score", "Total", "Percentage (%)", "Date Taken"])

    for r in rows:
        cw.writerow([r["attempt_id"], r["student_name"], r["student_email"], r["quiz_title"], r["category"], r["score"], r["total"], r["percentage"], r["taken_at"]])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=quizzy_student_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route("/admin/quiz/new", methods=["GET", "POST"])
@admin_required
def new_quiz():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()
        category = request.form.get("category", "General").strip()
        difficulty = request.form.get("difficulty", "Medium").strip()
        try:
            duration = min(max(1, int(request.form.get("duration", "10"))), 180)
        except ValueError:
            duration = 10

        if title:
            is_published = 1 if request.form.get("published") else 0
            with db() as con:
                cur = con.execute("""
                    INSERT INTO quizzes(title, description, category, difficulty, duration, published)
                    VALUES(?, ?, ?, ?, ?, ?)
                """, (title, desc, category, difficulty, duration, is_published))
                new_id = cur.lastrowid
            flash("Quiz created successfully! Now add questions for your students.", "success")
            return redirect(url_for("add_question", quiz_id=new_id))

        flash("Quiz title is required.", "danger")

    return render_template("quiz_form.html", quiz=None)


@app.route("/admin/quiz/<int:quiz_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_quiz(quiz_id):
    with db() as con:
        quiz = con.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()

    if not quiz:
        flash("Quiz not found.", "warning")
        return redirect(url_for("admin"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()
        category = request.form.get("category", "General").strip()
        difficulty = request.form.get("difficulty", "Medium").strip()
        try:
            duration = min(max(1, int(request.form.get("duration", "10"))), 180)
        except ValueError:
            duration = 10
        is_published = 1 if request.form.get("published") else 0

        if title:
            with db() as con:
                con.execute("""
                    UPDATE quizzes
                    SET title=?, description=?, category=?, difficulty=?, duration=?, published=?
                    WHERE id=?
                """, (title, desc, category, difficulty, duration, is_published, quiz_id))
            flash("Quiz updated successfully!", "success")
            return redirect(url_for("admin"))

        flash("Quiz title cannot be empty.", "danger")

    return render_template("quiz_form.html", quiz=quiz)


@app.route("/admin/quiz/<int:quiz_id>/delete", methods=["POST"])
@admin_required
def delete_quiz(quiz_id):
    with db() as con:
        con.execute("DELETE FROM quizzes WHERE id=?", (quiz_id,))
    flash("Quiz and its associated questions/results have been deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/quiz/<int:quiz_id>/question", methods=["GET", "POST"])
@admin_required
def add_question(quiz_id):
    with db() as con:
        quiz = con.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()

    if not quiz:
        flash("Quiz not found.", "warning")
        return redirect(url_for("admin"))

    if request.method == "POST":
        question_text = request.form.get("question", "").strip()
        opt_a = request.form.get("a", "").strip()
        opt_b = request.form.get("b", "").strip()
        opt_c = request.form.get("c", "").strip()
        opt_d = request.form.get("d", "").strip()
        correct = request.form.get("correct", "").strip().lower()
        explanation = request.form.get("explanation", "").strip()

        if question_text and opt_a and opt_b and opt_c and opt_d and correct in ("a", "b", "c", "d"):
            with db() as con:
                con.execute("""
                    INSERT INTO questions (quiz_id, question, a, b, c, d, correct, explanation)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """, (quiz_id, question_text, opt_a, opt_b, opt_c, opt_d, correct, explanation))
            flash("Question added successfully!", "success")
            return redirect(url_for("add_question", quiz_id=quiz_id))

        flash("Please complete all question fields and select the correct option.", "danger")

    with db() as con:
        questions = con.execute("""
            SELECT id, question, a, b, c, d, correct, explanation
            FROM questions
            WHERE quiz_id=?
            ORDER BY id ASC
        """, (quiz_id,)).fetchall()

    return render_template("question_form.html", quiz=quiz, questions=questions)


@app.route("/admin/question/<int:question_id>/delete", methods=["POST"])
@admin_required
def delete_question(question_id):
    quiz_id = request.form.get("quiz_id")
    with db() as con:
        con.execute("DELETE FROM questions WHERE id=?", (question_id,))
    flash("Question deleted successfully.", "info")
    if quiz_id:
        return redirect(url_for("add_question", quiz_id=quiz_id))
    return redirect(url_for("admin"))


@app.route("/admin/quiz/<int:quiz_id>/publish", methods=["POST"])
@admin_required
def toggle_publish(quiz_id):
    with db() as con:
        con.execute("UPDATE quizzes SET published = 1 - published WHERE id=?", (quiz_id,))
    flash("Quiz visibility toggled.", "info")
    return redirect(url_for("admin"))


# ==============================================================================
# Application Bootstrap
# ==============================================================================
# Run database setup on startup (idempotent; safe for Gunicorn & WSGI deployments)
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
