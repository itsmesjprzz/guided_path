from flask import Flask, render_template, request, session, jsonify, redirect, url_for, flash
from flask_mail import Mail, Message
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
from sqlalchemy import func
from threading import Thread
import os
import csv
import random
import string
import uuid
import pandas as pd
import traceback

from models import db, Enrollee, ActivityLog, StudentAnswer, ExamQuestion, ExamResult


app = Flask(__name__, static_folder="static")
database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is not set. Add it in Railway Variables.")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
           "pool_pre_ping": True,
           "pool_recycle": 300,
           }
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "secret"

app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp-relay.brevo.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")

app.config["MAIL_DEFAULT_SENDER"] = (
    "Admissions Office - Guided Path",
    os.environ.get("MAIL_SENDER_EMAIL")
)

app.config["MAIL_TIMEOUT"] = 10

db.init_app(app)
mail = Mail(app)

with app.app_context():
    db.create_all()


QUESTION_FIELDS = [
    "subject",
    "difficulty",
    "question_text",
    "choice_a",
    "choice_b",
    "choice_c",
    "choice_d",
    "correct_option",
]

SUBJECT_CLASS_MAP = {
    "Mathematics": "mathematics",
    "Science & Technology": "science",
    "Language & Communication": "language",
    "Reading Comprehension & Critical Thinking": "reading",
    "General Knowledge / Social Sciences": "general",
}

PROGRAMS = [
    {
        "name": "College of Computer Studies",
        "dept": "Computer and Information Technology",
        "weights": {
            "Mathematics": 5,
            "Science & Technology": 4,
            "Reading Comprehension & Critical Thinking": 4,
            "Language & Communication": 2,
            "General Knowledge / Social Sciences": 2,
        },
    },
    {
        "name": "College of Accountancy",
        "dept": "Accounting and Finance",
        "weights": {
            "Mathematics": 5,
            "Reading Comprehension & Critical Thinking": 4,
            "General Knowledge / Social Sciences": 3,
            "Language & Communication": 2,
            "Science & Technology": 2,
        },
    },
    {
        "name": "College of Business Administration",
        "dept": "Business and Management",
        "weights": {
            "Language & Communication": 4,
            "Reading Comprehension & Critical Thinking": 4,
            "General Knowledge / Social Sciences": 4,
            "Mathematics": 3,
            "Science & Technology": 1,
        },
    },
    {
        "name": "College of Entrepreneurship",
        "dept": "Enterprise and Innovation",
        "weights": {
            "Language & Communication": 5,
            "Reading Comprehension & Critical Thinking": 4,
            "General Knowledge / Social Sciences": 4,
            "Mathematics": 2,
            "Science & Technology": 1,
        },
    },
    {
        "name": "College of Education",
        "dept": "Teacher Education",
        "weights": {
            "Language & Communication": 5,
            "Reading Comprehension & Critical Thinking": 5,
            "General Knowledge / Social Sciences": 4,
            "Mathematics": 2,
            "Science & Technology": 1,
        },
    },
]

def send_reference_email_async(student_name, email, reference_code, expiration):
    try:
        with app.app_context():
            send_reference_email(student_name, email, reference_code, expiration)
    except Exception as exc:
        print("Email sending failed:", exc)

def generate_reference_code():
    year = datetime.now().year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"GRC-{year}-{suffix}"


def log_activity(action, user="System"):
    db.session.add(ActivityLog(action=action, user=user))
    db.session.commit()


def clean_subject_class(subject_name):
    return SUBJECT_CLASS_MAP.get(subject_name, "general")


def normalize_subject(value):
    raw = (value or "").strip()

    aliases = {
        "Math": "Mathematics",
        "Mathematics": "Mathematics",
        "Science": "Science & Technology",
        "Science & Technology": "Science & Technology",
        "English": "Language & Communication",
        "Filipino": "Language & Communication",
        "Language": "Language & Communication",
        "Language & Communication": "Language & Communication",
        "Reading": "Reading Comprehension & Critical Thinking",
        "Reading Comprehension": "Reading Comprehension & Critical Thinking",
        "Critical Thinking": "Reading Comprehension & Critical Thinking",
        "Reading Comprehension & Critical Thinking": "Reading Comprehension & Critical Thinking",
        "General Knowledge": "General Knowledge / Social Sciences",
        "Social Sciences": "General Knowledge / Social Sciences",
        "General Knowledge / Social Sciences": "General Knowledge / Social Sciences",
    }

    return aliases.get(raw, raw)


def get_subject_totals():
    totals = {}
    for question in ExamQuestion.query.all():
        subject = question.subject
        totals[subject] = totals.get(subject, 0) + 1
    return totals


def get_result_breakdown(result_id):
    scores = {}
    totals = get_subject_totals()

    answers = StudentAnswer.query.filter_by(exam_result_id=result_id).all()
    for answer in answers:
        question = ExamQuestion.query.get(answer.question_id)
        if not question:
            continue

        scores.setdefault(question.subject, 0)
        if answer.is_correct:
            scores[question.subject] += 1

    return scores, totals


def compute_match(program, subject_scores, subject_totals):
    weighted_score = 0
    weighted_total = 0

    for subject, weight in program["weights"].items():
        weighted_score += subject_scores.get(subject, 0) * weight
        weighted_total += subject_totals.get(subject, 0) * weight

    if weighted_total == 0:
        return 0

    return round((weighted_score / weighted_total) * 100)


def get_recommendation(total_correct, total_questions, subject_scores, subject_totals):
    percentage = round((total_correct / total_questions) * 100) if total_questions else 0

    ranked = []
    for program in PROGRAMS:
        ranked.append({
            "name": program["name"],
            "dept": program["dept"],
            "match": compute_match(program, subject_scores, subject_totals),
        })

    ranked.sort(key=lambda item: item["match"], reverse=True)

    if percentage >= 75:
        standing = "Qualified"
    elif percentage >= 50:
        standing = "Conditionally Recommended"
    else:
        standing = "Not Yet Ready"

    top = ranked[0] if ranked else {"name": "No Program Match", "match": 0, "dept": ""}
    return top, ranked[:3], standing


def send_reference_email(student_name, email, reference_code, expiration):
    html = f"""
    <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.5;">
        <h2 style="color: #b91c1c;">GUIDED PATH: REFERENCE CODE</h2>
        <p>Dear Mr./Ms. {student_name},</p>
        <p>Thank you for registering for the entrance exam. Your unique reference code is:</p>
        <div style="background-color: #f3f4f6; padding: 15px; border-radius: 5px; font-size: 18px; font-weight: bold; text-align: center; margin: 20px 0;">
            {reference_code}
        </div>
        <p>This reference code is valid until <strong>{expiration.strftime('%Y-%m-%d %H:%M UTC')}</strong>.</p>
        <p>Best regards,<br>Admissions Office</p>
    </div>
    """

    msg = Message(
        subject="Official Entrance Examination Reference Code - Admissions Office",
        sender=app.config["MAIL_DEFAULT_SENDER"],
        recipients=[email],
        html=html,
    )
    mail.send(msg)


def send_result_email(student, result):
    msg = Message(
        subject="Your Entrance Exam Results",
        sender=app.config["MAIL_DEFAULT_SENDER"],
        recipients=[student.email],
        html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 650px; margin: auto; border: 1px solid #ddd;">

    <!-- HEADER -->
    <div style="background-color: #800000; color: white; padding: 15px; text-align: center;">
        <h2 style="margin: 0;">GUIDED PATH SYSTEM</h2>
        <p style="margin: 0; font-size: 14px;">Entrance Examination Result</p>
    </div>

    <!-- BODY -->
    <div style="padding: 20px;">

        <p>Dear <strong>{student.name}</strong>,</p>

        <p>
            Greetings! We are pleased to inform you that your entrance examination
            has been successfully completed. Below are your official results:
        </p>

        <!-- RESULT TABLE -->
        <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
            <tr>
                <td style="border: 1px solid #ccc; padding: 10px;"><strong>Score</strong></td>
                <td style="border: 1px solid #ccc; padding: 10px;">
                    {result.correct_answers} / {result.total_questions}
                </td>
            </tr>

            <tr>
                <td style="border: 1px solid #ccc; padding: 10px;"><strong>Recommended Program</strong></td>
                <td style="border: 1px solid #ccc; padding: 10px;">
                    {result.recommended_program}
                </td>
            </tr>

            <tr>
                <td style="border: 1px solid #ccc; padding: 10px;"><strong>Program Match</strong></td>
                <td style="border: 1px solid #ccc; padding: 10px;">
                    {result.match_percentage}%
                </td>
            </tr>

            <tr>
                <td style="border: 1px solid #ccc; padding: 10px;"><strong>Evaluation Status</strong></td>
                <td style="border: 1px solid #ccc; padding: 10px;">
                    {result.qualification_status}
                </td>
            </tr>
        </table>

        <!-- NOTE -->
        <p style="margin-top: 20px; font-size: 14px;">
            <em>
            Note: The recommended program is based on your performance across different subject areas.
            This serves as a guide to help you choose the most suitable academic path.
            </em>
        </p>

        <p>
            Should you have any questions, feel free to contact the admissions office.
        </p>

        <p style="margin-top: 25px;">
            Respectfully,<br>
            <strong>Admissions Office</strong><br>
            Guided Path System
        </p>

    </div>

    <!-- FOOTER -->
    <div style="background-color: #f2f2f2; padding: 10px; text-align: center; font-size: 12px; color: #555;">
        This is a system-generated email. Please do not reply.
    </div>

    </div>
    """,
    )
    mail.send(msg)


@app.after_request
def prevent_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response


@app.route("/")
def home():
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/admin")
def admin_dashboard():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    if username == "admin" and password == "admin123":
        session["admin_id"] = 1
        session["fullname"] = "Administrator"
        return redirect(url_for("dashboard"))

    return render_template("login.html", error="Invalid Credentials")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if "admin_id" not in session:
        return redirect(url_for("home"))

    return render_template(
        "admin_dashboard.html",
        fullname=session.get("fullname", "Administrator"),
        recent_activities=ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(5).all(),
        total_enrolled=Enrollee.query.count(),
        currently_taking=Enrollee.query.filter_by(status="in_progress").count(),
        finished_exams=Enrollee.query.filter_by(status="completed").count(),
    )


@app.route("/student")
def student_home():
    return render_template("student_dashboard.html")


@app.route("/student/login")
def student_login():
    return render_template("student_login.html")


@app.route("/student/authenticate", methods=["POST"])
def student_authenticate():
    data = request.get_json() or {}
    reference_code = (data.get("reference_code") or "").strip()

    if not reference_code:
        return jsonify({"success": False, "message": "Reference code is required."})

    student = Enrollee.query.filter_by(reference_code=reference_code).first()
    if not student:
        return jsonify({"success": False, "message": "Invalid reference code."})

    if student.reference_expiration and datetime.utcnow() > student.reference_expiration:
        return jsonify({"success": False, "message": "Reference code has expired."})

    session["student_id"] = student.id
    return jsonify({"success": True, "message": "Login successful"})


@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Enrollee.query.get(session["student_id"])
    return render_template("student_dashboard.html", student=student)


@app.route("/student/register", methods=["POST"])
def student_register():
    data = request.get_json() or {}
    required = ["full_name", "email", "contact_number"]

    missing = [field for field in required if not (data.get(field) or "").strip()]
    if missing:
        return jsonify({
            "success": False,
            "message": f"Missing required fields: {', '.join(missing)}",
        }), 400

    reference_code = generate_reference_code()
    while Enrollee.query.filter_by(reference_code=reference_code).first():
        reference_code = generate_reference_code()

    expiration = datetime.now(timezone.utc) + timedelta(hours=24)

    enrollee = Enrollee(
        name=data["full_name"].strip(),
        email=data["email"].strip(),
        contact_number=data["contact_number"].strip(),
        school_strand=(data.get("school_strand") or "").strip(),
        reference_code=reference_code,
        reference_expiration=expiration,
        status="not_started",
        registration_date=datetime.utcnow(),
    )

    db.session.add(enrollee)
    db.session.commit()

    Thread(
        target=send_reference_email_async,
        args=(enrollee.name, enrollee.email, reference_code, expiration),
        daemon=True
    ).start()

    return jsonify({
        "success": True,
        "message": "Registration successful. Please check your email for the reference code.",
        "reference_code": reference_code
    })  

@app.route("/student/exam")
def student_exam():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("student_login"))

    student = Enrollee.query.get(student_id)
    if not student:
        return "Student not found", 404

    if student.status == "completed":
        latest_result = ExamResult.query.filter_by(student_id=student.id, exam_type="main").order_by(ExamResult.created_at.desc()).first()
        if latest_result:
            return redirect(url_for("student_result", result_id=latest_result.id))

    questions = ExamQuestion.query.all()
    random.shuffle(questions)

    return render_template(
        "student_main_exam.html",
        questions=[q.to_dict() for q in questions],
        duration=60,
        student=student,
    )


@app.route("/api/enrollee/start_exam/<int:enrollee_id>", methods=["POST"])
def start_exam_api(enrollee_id):
    enrollee = Enrollee.query.get(enrollee_id)
    if not enrollee:
        return jsonify({"success": False, "error": "Enrollee not found"}), 404

    if enrollee.status == "not_started":
        enrollee.status = "in_progress"
        db.session.commit()

    return jsonify({"success": True})


@app.route("/student/submit_exam", methods=["POST"])
def submit_exam():
    student_id = session.get("student_id")
    if not student_id:
        return jsonify({"error": "Not logged in"}), 401

    student = Enrollee.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    existing_result = ExamResult.query.filter_by(
        student_id=student.id,
        exam_type="main",
        status="completed",
    ).first()

    if existing_result:
        return jsonify({
            "success": True,
            "exam_result_id": existing_result.id,
            "message": "Exam already submitted.",
        })

    data = request.get_json() or {}
    submitted_answers = data.get("answers") or {}
    if not submitted_answers:
        return jsonify({"error": "No answers submitted"}), 400

    subject_scores = {}
    subject_totals = get_subject_totals()
    total_correct = 0
    total_questions = 0

    exam_result = ExamResult(
        student_id=student.id,
        exam_type="main",
        correct_answers=0,
        total_questions=0,
        status="completed",
    )

    db.session.add(exam_result)
    db.session.flush()

    for question_id, selected in submitted_answers.items():
        question = ExamQuestion.query.get(int(question_id)) if str(question_id).isdigit() else None
        if not question:
            continue

        total_questions += 1
        subject_scores.setdefault(question.subject, 0)

        selected_answer = str(selected).strip().upper()
        is_correct = selected_answer == question.correct_option.strip().upper()

        if is_correct:
            total_correct += 1
            subject_scores[question.subject] += 1

        db.session.add(StudentAnswer(
            exam_result_id=exam_result.id,
            question_id=question.id,
            selected_answer=selected_answer,
            is_correct=is_correct,
        ))

    recommendation, alternatives, standing = get_recommendation(
        total_correct,
        total_questions,
        subject_scores,
        subject_totals,
    )

    exam_result.correct_answers = total_correct
    exam_result.total_questions = total_questions
    exam_result.recommended_program = recommendation["name"]
    exam_result.match_percentage = recommendation["match"]
    exam_result.qualification_status = standing if hasattr(exam_result, "qualification_status") else None

    student.status = "completed"
    student.exam_date = datetime.utcnow().date()

    db.session.commit()

    try:
        send_result_email(student, exam_result)
    except Exception as exc:
        print("Result email was not sent:", exc)

    return jsonify({
        "success": True,
        "exam_result_id": exam_result.id,
    })


@app.route("/student/result")
def student_result():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("student_login"))

    result_id = request.args.get("result_id")
    if not result_id:
        return {"error": "Exam result not specified"}, 400

    exam_result = ExamResult.query.get(int(result_id))
    if not exam_result or exam_result.student_id != student_id:
        return {"error": "Exam result not found"}, 404

    student = Enrollee.query.get(student_id)
    subject_scores, subject_totals = get_result_breakdown(exam_result.id)

    return render_template(
        "student_result.html",
        student=student,
        exam_result=exam_result,
        answers=exam_result.answers,
        total_correct=exam_result.correct_answers,
        total_questions=exam_result.total_questions,
        subject_scores=subject_scores,
        subject_totals=subject_totals,
    )


@app.route("/student/email_results")
def email_results():
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for("student_login"))

    result = ExamResult.query.filter_by(student_id=student_id, exam_type="main").order_by(ExamResult.created_at.desc()).first()
    student = Enrollee.query.get(student_id)

    if not result or not student:
        flash("No result found.", "danger")
        return redirect(url_for("student_dashboard"))

    try:
        send_result_email(student, result)
        flash("Your results have been emailed successfully.", "success")
    except Exception as exc:
        flash(f"Unable to send email: {exc}", "danger")

    return redirect(url_for("student_result", result_id=result.id))


@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    return redirect(url_for("student_login"))


@app.route("/results")
def results():
    if "admin_id" not in session:
        return redirect(url_for("home"))
    return render_template("results.html")


@app.route("/api/results")
def api_results():
    records = []

    results = ExamResult.query.order_by(ExamResult.created_at.desc()).all()
    for result in results:
        student = Enrollee.query.get(result.student_id)
        if not student:
            continue

        subject_scores, subject_totals = get_result_breakdown(result.id)

        records.append({
            "result_id": result.id,
            "student_id": student.id,
            "name": student.name,
            "email": student.email,
            "contact_number": student.contact_number,
            "school_strand": student.school_strand,
            "reference_code": student.reference_code,
            "registration_date": student.registration_date.isoformat() if student.registration_date else None,
            "date_taken": result.created_at.strftime("%Y-%m-%d %H:%M") if result.created_at else None,
            "status": student.status,
            "score": result.correct_answers,
            "total_questions": result.total_questions,
            "recommended_program": result.recommended_program,
            "match_percentage": result.match_percentage,
            "subject_scores": subject_scores,
            "subject_totals": subject_totals,
        })

    return jsonify({"success": True, "results": records})


@app.route("/admin/exam-set")
def admin_exam_set():
    if "admin_id" not in session:
        return redirect(url_for("home"))

    questions = ExamQuestion.query.order_by(ExamQuestion.id.desc()).all()

    subject_counts = (
        db.session.query(ExamQuestion.subject, func.count(ExamQuestion.id))
        .group_by(ExamQuestion.subject)
        .all()
    )

    subjects = [
        {
            "name": subject,
            "count": count,
            "class_name": clean_subject_class(subject),
        }
        for subject, count in subject_counts
    ]

    return render_template("admin_exam_set.html", questions=questions, subjects=subjects)


@app.route("/import_questions", methods=["POST"])
def import_questions():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please select a CSV file.", "danger")
        return redirect(url_for("admin_exam_set"))

    if not file.filename.lower().endswith(".csv"):
        flash("Only CSV files are accepted.", "danger")
        return redirect(url_for("admin_exam_set"))

    rows = file.stream.read().decode("utf-8-sig", errors="ignore").splitlines()
    reader = csv.DictReader(rows)

    if not reader.fieldnames:
        flash("CSV file is empty or invalid.", "danger")
        return redirect(url_for("admin_exam_set"))

    reader.fieldnames = [field.strip().replace("\ufeff", "") for field in reader.fieldnames]

    inserted = 0
    skipped = 0

    for index, row in enumerate(reader, start=1):
        row = {
            (key or "").strip().replace("\ufeff", ""): (value or "").strip()
            for key, value in row.items()
        }

        missing = [field for field in QUESTION_FIELDS if not row.get(field)]
        if missing:
            skipped += 1
            print(f"Row {index} skipped: missing {missing}")
            continue

        try:
            db.session.add(ExamQuestion(
                subject=normalize_subject(row["subject"]),
                difficulty=row["difficulty"].title(),
                question_text=row["question_text"],
                choice_a=row["choice_a"],
                choice_b=row["choice_b"],
                choice_c=row["choice_c"],
                choice_d=row["choice_d"],
                correct_option=row["correct_option"].upper(),
                date_added=datetime.utcnow(),
            ))
            inserted += 1
        except Exception as exc:
            skipped += 1
            print(f"Row {index} skipped: {exc}")

    db.session.commit()
    flash(f"{inserted} question(s) imported. {skipped} row(s) skipped.", "success" if inserted else "warning")
    return redirect(url_for("admin_exam_set"))


@app.route("/admin/exam-set/main/add", methods=["GET", "POST"])
def add_main_exam_question():
    if request.method == "POST":
        question = ExamQuestion(
            subject=normalize_subject(request.form.get("subject")),
            difficulty=(request.form.get("difficulty") or "").title(),
            question_text=request.form.get("question_text"),
            choice_a=request.form.get("choice_a"),
            choice_b=request.form.get("choice_b"),
            choice_c=request.form.get("choice_c"),
            choice_d=request.form.get("choice_d"),
            correct_option=(request.form.get("correct_answer") or "").upper(),
            date_added=datetime.utcnow(),
        )

        db.session.add(question)
        db.session.commit()

        log_activity(f"Added exam question for {question.subject}", user="Administrator")
        return redirect(url_for("admin_exam_set"))

    return render_template("add_main_exam_question.html")


@app.route("/api/questions/<int:question_id>", methods=["GET"])
def api_get_question(question_id):
    question = ExamQuestion.query.get_or_404(question_id)

    return jsonify({
        "success": True,
        "question": question.to_dict(),
    })


@app.route("/api/questions/<int:question_id>", methods=["PUT"])
def api_update_question(question_id):
    data = request.get_json() or {}
    question = ExamQuestion.query.get_or_404(question_id)

    for field in QUESTION_FIELDS:
        if field in data:
            value = data[field]
            if field == "subject":
                value = normalize_subject(value)
            elif field == "difficulty":
                value = value.title()
            elif field == "correct_option":
                value = value.upper()
            setattr(question, field, value)

    db.session.commit()
    log_activity(f"Edited exam question #{question_id}", user="Administrator")

    return jsonify({"success": True})


@app.route("/admin/update_question/<int:question_id>", methods=["POST"])
def update_question_from_modal(question_id):
    data = request.get_json() or {}
    question = ExamQuestion.query.get_or_404(question_id)

    for field in QUESTION_FIELDS:
        if field in data:
            value = data[field]
            if field == "subject":
                value = normalize_subject(value)
            elif field == "difficulty":
                value = value.title()
            elif field == "correct_option":
                value = value.upper()
            setattr(question, field, value)

    db.session.commit()
    return jsonify({"success": True})


@app.route("/admin/exam-set/main/delete/<int:question_id>")
def delete_question(question_id):
    question = ExamQuestion.query.get_or_404(question_id)
    db.session.delete(question)
    db.session.commit()

    log_activity(f"Deleted exam question #{question_id}", user="Administrator")
    return redirect(url_for("admin_exam_set"))


@app.route("/admin/delete_question/<int:question_id>", methods=["POST"])
def delete_question_ajax(question_id):
    question = ExamQuestion.query.get_or_404(question_id)
    db.session.delete(question)
    db.session.commit()

    log_activity(f"Deleted exam question #{question_id}", user="Administrator")
    return jsonify({"success": True})


@app.route("/admin/delete_all_questions", methods=["POST"])
def delete_all_questions():
    count = ExamQuestion.query.delete()
    db.session.commit()

    log_activity(f"Deleted all exam questions ({count})", user="Administrator")
    flash(f"{count} question(s) deleted.", "success")
    return redirect(url_for("admin_exam_set"))


@app.route("/admin/enrollees")
def admin_enrollees():
    if "admin_id" not in session:
        return redirect(url_for("home"))
    return render_template("enrollees.html")


@app.route("/api/enrollees", methods=["GET"])
def get_enrollees():
    enrollees = Enrollee.query.order_by(Enrollee.created_at.desc()).all()

    return jsonify({
        "success": True,
        "enrollees": [item.to_dict() for item in enrollees],
        "total_enrolled": Enrollee.query.count(),
        "active_count": Enrollee.query.filter_by(status="in_progress").count(),
        "finished_count": Enrollee.query.filter_by(status="completed").count(),
        "not_started_count": Enrollee.query.filter_by(status="not_started").count(),
        "in_progress_count": Enrollee.query.filter_by(status="in_progress").count(),
        "completed_count": Enrollee.query.filter_by(status="completed").count(),
    })


@app.route("/api/enrollees", methods=["POST"])
def add_enrollee():
    data = request.get_json() or {}

    if not data.get("name") or not data.get("email"):
        return jsonify({"success": False, "error": "Name and email are required."}), 400

    reference_code = generate_reference_code()
    while Enrollee.query.filter_by(reference_code=reference_code).first():
        reference_code = generate_reference_code()

    enrollee = Enrollee(
        name=data["name"].strip(),
        email=data["email"].strip(),
        contact_number=(data.get("contact_number") or "").strip(),
        reference_code=reference_code,
        status="not_started",
        registration_date=datetime.utcnow(),
        exam_date=None,
        time_taken=data.get("time_taken"),
        time_accomplished=data.get("time_accomplished"),
    )

    db.session.add(enrollee)
    db.session.commit()

    log_activity(f"Added enrollee: {enrollee.name} ({enrollee.reference_code})", user="Administrator")
    return jsonify({"success": True, "reference_code": reference_code, "id": enrollee.id}), 201


@app.route("/api/enrollees/<int:enrollee_id>", methods=["PUT"])
def edit_enrollee(enrollee_id):
    data = request.get_json() or {}
    enrollee = Enrollee.query.get_or_404(enrollee_id)

    for field in ["name", "email", "status", "time_taken", "time_accomplished"]:
        if field in data:
            setattr(enrollee, field, data[field])

    db.session.commit()
    log_activity(f"Edited enrollee: {enrollee.name}", user="Administrator")

    return jsonify({"success": True, "enrollee": enrollee.to_dict()})


@app.route("/api/enrollees/<int:enrollee_id>", methods=["DELETE"])
def delete_enrollee(enrollee_id):
    enrollee = Enrollee.query.get_or_404(enrollee_id)
    db.session.delete(enrollee)
    db.session.commit()

    log_activity(f"Deleted enrollee: {enrollee.name}", user="Administrator")
    return jsonify({"success": True})


@app.route("/admin/enrollees/import", methods=["POST"])
def import_enrollees():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    if not file.filename.lower().endswith((".csv", ".xlsx")):
        return jsonify({"success": False, "error": "Invalid file type"}), 400

    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(TextIOWrapper(file, encoding="utf-8-sig"))
        else:
            df = pd.read_excel(file)

        entries = []

        for _, row in df.iterrows():
            name = row.get("Name")
            email = row.get("Email")

            if pd.isna(name) or pd.isna(email):
                continue

            reference_code = row.get("Reference Code")
            if pd.isna(reference_code) or not str(reference_code).strip():
                reference_code = f"GRC-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

            registration_date = row.get("Date of Registration")
            if pd.isna(registration_date):
                registration_date = datetime.utcnow().date()
            else:
                registration_date = pd.to_datetime(registration_date).date()

            exam_date = row.get("Exam Date")
            exam_date = None if pd.isna(exam_date) else pd.to_datetime(exam_date).date()

            status = row.get("Status")
            status = "not_started" if pd.isna(status) or not str(status).strip() else str(status).strip()

            entries.append(Enrollee(
                name=str(name).strip(),
                email=str(email).strip(),
                contact_number=None if pd.isna(row.get("Contact Number")) else str(row.get("Contact Number")).strip(),
                school_strand=None if pd.isna(row.get("School/Strand")) else str(row.get("School/Strand")).strip(),
                reference_code=str(reference_code).strip(),
                status=status,
                registration_date=registration_date,
                exam_date=exam_date,
            ))

        db.session.bulk_save_objects(entries)
        db.session.commit()

        return jsonify({"success": True, "message": f"{len(entries)} enrollees imported successfully."})

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))