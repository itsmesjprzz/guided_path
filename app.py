from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort
from flask_mail import Mail, Message
from models import ExamQuestion
from datetime import datetime, timedelta, timezone
import random, string,  traceback
import csv
import uuid
import pandas as pd
from io import TextIOWrapper
from models import db, MainExamQuestion, Enrollee, ActivityLog
from sqlalchemy import func
from werkzeug.utils import secure_filename
from sqlalchemy.orm import Session

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///guided_path.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'secret'

db.init_app(app)
with app.app_context():
    db.create_all()

# email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'iaaanmendaro16@gmail.com'
app.config['MAIL_PASSWORD'] = 'xnhn acaf vfzv ysnk'  # Gmail app password if using 2FA
app.config['MAIL_DEFAULT_SENDER'] = 'iaaanmendaro16@gmail.com'

# Initialize Flask-Mail
mail = Mail(app)

# admin dashboard route
@app.route('/admin')
def admin_dashboard():
    return render_template('login.html')

# student dashboard route

@app.route('/student/login')
def student_login():
    return render_template('student_login.html')

@app.route('/student')
def student_home():
    return render_template('student_dashboard.html')

# student Authentication Code

@app.route('/student/authenticate', methods=['POST'])
def student_authenticate():
    data = request.get_json()
    reference_code = data.get("reference_code")

    if not reference_code:
        return jsonify({"success": False, "message": "Reference code is required."})

    # Lookup student by reference code
    student = Enrollee.query.filter_by(reference_code=reference_code).first()

    if not student:
        return jsonify({"success": False, "message": "Invalid or inactive reference code."})
    
    if student.reference_expiration and datetime.utcnow() > student.reference_expiration:
        return jsonify({"success": False, "message": "Reference code has expired."})

    # Store student ID in session
    session['student_id'] = student.id
    return jsonify({"success": True, "message": "Login successful"})

# Student Dashboard Route

@app.route('/student/dashboard')
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/student/login')

    student = Enrollee.query.get(session['student_id'])
    return render_template('student_dashboard.html', student=student)

# student register

@app.route('/student/register', methods=['POST'])
def student_register():
    data = request.get_json()

    # Required fields
    required = ['full_name', 'email', 'contact_number']
    missing = [field for field in required if field not in data or not data[field].strip()]
    if missing:
        return jsonify({
            'success': False,
            'message': f"Missing required fields: {', '.join(missing)}"
        }), 400

    # Generate unique reference code
    ref_code = generate_reference_code()
    while Enrollee.query.filter_by(reference_code=ref_code).first():
        ref_code = generate_reference_code()

    expiration = datetime.now(timezone.utc) + timedelta(hours=24)
    registration_date = datetime.now(timezone.utc)

    # Create enrollee record in the existing Enrollee table
    new_enrollee = Enrollee(
        name=data['full_name'].strip(),
        email=data['email'].strip(),
        contact_number=data['contact_number'].strip(),
        school_strand=data.get('school_strand', '').strip(),
        reference_code=ref_code,
        reference_expiration=expiration,
        status='not_started',
        registration_date=datetime.utcnow()
    )

    db.session.add(new_enrollee)
    db.session.commit()

    try:
        msg = Message(
    subject="Entrance Exam Reference Code | [Your College Name]",
    sender=app.config['MAIL_USERNAME'],
    recipients=[data['email'].strip()],
    html=f"""
    <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.5;">
        <h2 style="color: #b91c1c;">GUIDED PATH: REFERENCE CODE</h2>
        <p>Dear {data['full_name']},</p>
        
        <p>Thank you for registering for the upcoming entrance exam. Your unique reference code is provided below:</p>
        
        <div style="background-color: #f3f4f6; padding: 15px; border-radius: 5px; font-size: 18px; font-weight: bold; text-align: center; margin: 20px 0;">
            {ref_code}
        </div>
        
        <p>Please note that this reference code is valid until <strong>{expiration.strftime('%Y-%m-%d %H:%M UTC')}</strong>. 
        Make sure to use it before it expires to access the entrance exam.</p>
        
        <p>If you did not register for the exam, please disregard this message.</p>
        
        <p style="margin-top: 30px;">Best regards,<br>
        Admissions Office<br>
        Mr. Harry D. Dela Rosa</p>
        
        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
        <p style="font-size: 12px; color: #888;">
            This is an automated message from our system. Please do not reply to this email.
        </p>
    </div>
    """
)
        mail.send(msg)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration successful, but failed to send email: {e}'})
    
    return jsonify({
        'success': True,
        'message': 'Registration successful! Check your email for the reference code.'
    })

# -------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------

def generate_reference_code(length=12):
    """Generate a random reference code like 'GRC-2025-KIS07'."""
    prefix = "GRC-2025-"
    # Generate 4 random uppercase letters/numbers
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return prefix + suffix

def log_activity(action, user="System"):
    """Record an admin or system activity."""
    new_log = ActivityLog(action=action, user=user)
    db.session.add(new_log)
    db.session.commit()

# insert csv

@app.route('/import_questions', methods=['POST'])
def import_questions():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('admin_exam_set'))

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('admin_exam_set'))

    if file:
        # Read CSV
        stream = file.stream.read().decode("UTF-8").splitlines()
        csv_reader = csv.DictReader(stream)
        for row in csv_reader:
            question = MainExamQuestion(
                subject=row['subject'],
                difficulty=row['difficulty'],
                question_text=row['question_text'],
                choice_a=row['choice_a'],
                choice_b=row['choice_b'],
                choice_c=row['choice_c'],
                choice_d=row['choice_d'],
                correct_option=row['correct_option']
            )
            db.session.add(question)
        db.session.commit()
        flash('Questions imported successfully.')
    return redirect(url_for('admin_exam_set'))
    
# -------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------
@app.route('/')
def home():
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username == 'admin' and password == 'admin123':
        session['admin_id'] = 1
        session['fullname'] = "Administrator"
        return redirect(url_for('dashboard'))
    return render_template('login.html', error='Invalid Credentials')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# -------------------------------------------------
# ADMIN DASHBOARD
# -------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('home'))
    
    recent_activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(5).all()

    total_enrolled = Enrollee.query.count()
    currently_taking = Enrollee.query.filter_by(status='in_progress').count()
    finished_exams = Enrollee.query.filter_by(status='completed').count()

    return render_template(
        'admin_dashboard.html',
        fullname=session.get('fullname', 'Administrator'),
        recent_activities=recent_activities,
        total_enrolled=total_enrolled,
        currently_taking=currently_taking,
        finished_exams=finished_exams
    )

# STUDENT DASHBOARD

#student exam

@app.route('/student/exam')
def student_exam():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))

    student = Enrollee.query.get(session['student_id'])
    questions = MainExamQuestion.query.order_by(MainExamQuestion.id).all()
    duration = 60  # exam duration in minutes
    return render_template('student_main_exam.html', student=student, questions=questions, duration=duration)

#student submit exam

@app.route('/student/start_exam', methods=['POST'])
def starts_exam():
    student = Enrollee.query.get(session['student_id'])
    if student.status == 'not_started':
        student.status = 'in_progress'
        db.session.commit()
    return jsonify({'success': True})

# student start exam

@app.route('/api/enrollee/start_exam/<int:enrollee_id>', methods=['POST'])
def start_exam_api(enrollee_id):
    enrollee = Enrollee.query.get(enrollee_id)
    if not enrollee:
        return jsonify({'success': False, 'error': 'Enrollee not found'}), 404

    # Only update if not already started
    if enrollee.status == 'not_started':
        enrollee.status = 'in_progress'
        db.session.commit()

    return jsonify({'success': True, 'new_status': enrollee.status})

@app.route('/student/submit_exam', methods=['POST'])
def submit_exam():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'error': 'Student not logged in'}), 401

    student = Enrollee.query.get(student_id)
    if not student:
        return jsonify({'success': False, 'error': 'Student not found'}), 404

    student.status = 'completed'
    db.session.commit()
    return jsonify({'success': True, 'new_status': student.status})

#student logout
@app.route('/student/logout')
def student_logout():
    session.pop('student_id', None)
    return redirect(url_for('student_login'))


# -------------------------------------------------
# EXAM MANAGEMENT
# -------------------------------------------------
@app.route('/admin/exam-set')
def admin_exam_set():
    # Get all questions
    questions = MainExamQuestion.query.order_by(MainExamQuestion.id.desc()).all()

    # Get subject counts
    subjects_counts = (
        db.session.query(
            MainExamQuestion.subject,
            func.count(MainExamQuestion.id).label('count')
        )
        .group_by(MainExamQuestion.subject)
        .all()
    )

    subjects = []
    for sc in subjects_counts:
        subjects.append({
            'name': sc.subject,
            'count': sc.count,
            'class_name': sc.subject.lower()
        })

    return render_template('admin_exam_set.html', questions=questions, subjects=subjects)

# Add New Question
@app.route('/admin/exam-set/main/add', methods=['GET', 'POST'])
def add_main_exam_question():
    if request.method == 'POST':
        new_question = MainExamQuestion(
            subject=request.form.get('subject'),
            difficulty=request.form.get('difficulty'),
            question_text=request.form.get('question_text'),
            choice_a=request.form.get('choice_a'),
            choice_b=request.form.get('choice_b'),
            choice_c=request.form.get('choice_c'),
            choice_d=request.form.get('choice_d'),
            correct_option=request.form.get('correct_answer'),
            date_added=datetime.now()
        )

        db.session.add(new_question)
        db.session.commit()
        log_activity(f"Added new exam question for subject: {new_question.subject}")
        return redirect(url_for('admin_exam_set'))

    return render_template('add_main_exam_question.html')

# -------------------------------------------------
# ENROLLEE MANAGEMENT
# -------------------------------------------------
@app.route('/admin/enrollees')
def admin_enrollees():
    if 'admin_id' not in session:
        return redirect(url_for('home'))
    return render_template('enrollees.html')

@app.route('/api/enrollees', methods=['GET'])
def get_enrollees():
    enrollees = Enrollee.query.order_by(Enrollee.created_at.desc()).all()
    total_enrolled = Enrollee.query.count()
    not_started_count = Enrollee.query.filter_by(status='not_started').count()
    in_progress_count = Enrollee.query.filter_by(status='in_progress').count()
    completed_count = Enrollee.query.filter_by(status='completed').count()

    return jsonify({
        'success': True,
        'enrollees': [e.to_dict() for e in enrollees],
        'total_enrolled': total_enrolled,
        'active_count': in_progress_count,
        'finished_count': completed_count,
        'not_started_count': not_started_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count
    })

@app.route('/api/enrollees', methods=['POST'])
def add_enrollee():
    data = request.get_json()
    if not data or 'name' not in data or 'email' not in data:
        return jsonify({'success': False, 'error': 'Missing name or email'}), 400

    ref_code = generate_reference_code()
    while Enrollee.query.filter_by(reference_code=ref_code).first():
        ref_code = generate_reference_code()

    new_enrollee = Enrollee(
        name=data['name'],
        email=data['email'],
        contact_number=data['contact_number'],
        reference_code=ref_code,
        status='not_started',
        registration_date=datetime.today(),
        exam_date=None,
        time_taken=data.get('time_taken'),
        time_accomplished=data.get('time_accomplished')
    )

    db.session.add(new_enrollee)
    db.session.commit()
    log_activity(f"Added new enrollee: {new_enrollee.name} ({new_enrollee.reference_code})", user="Administrator")

    return jsonify({'success': True, 'reference_code': ref_code, 'id': new_enrollee.id}), 201

@app.route('/api/enrollees/<int:enrollee_id>', methods=['PUT'])
def edit_enrollee(enrollee_id):
    data = request.get_json()
    enrollee = Enrollee.query.get_or_404(enrollee_id)

    for field in ['name', 'email', 'status', 'time_taken', 'time_accomplished']:
        if field in data:
            setattr(enrollee, field, data[field])

    db.session.commit()
    log_activity(f"Edited enrollee: {enrollee.name} (Ref: {enrollee.reference_code})")

    return jsonify({'success': True, 'enrollee': enrollee.to_dict()})

@app.route('/api/enrollees/<int:enrollee_id>', methods=['DELETE'])
def delete_enrollee(enrollee_id):
    enrollee = Enrollee.query.get_or_404(enrollee_id)
    db.session.delete(enrollee)
    db.session.commit()

    log_activity(f"Deleted enrollee: {enrollee.name} (Ref: {enrollee.reference_code})")
    return jsonify({'success': True})


@app.route('/results')
def results():
    enrollees = Enrollee.query.filter_by(status='completed').all()
    return render_template('results.html', enrollees=enrollees)

@app.route('/admin/exam-set/main/delete/<int:id>')
def delete_question(id):
    question = MainExamQuestion.query.get_or_404(id)
    db.session.delete(question)
    db.session.commit()
    log_activity(f"Deleted exam question ID: {id}", user="Administrator")
    return redirect(url_for('admin_exam_set'))

@app.route('/api/questions/<int:id>', methods=['GET'])
def api_get_question(id):
    q = MainExamQuestion.query.get_or_404(id)
    return jsonify({
        "success": True,
        "question": {
            "id": q.id,
            "subject": q.subject,
            "difficulty": q.difficulty,
            "date_added": q.date_added.strftime('%Y-%m-%d') if q.date_added else None,
            "question_text": q.question_text,
            "choice_a": q.choice_a,
            "choice_b": q.choice_b,
            "choice_c": q.choice_c,
            "choice_d": q.choice_d,
            "correct_option": q.correct_option
        }
    })

@app.route('/api/questions/<int:id>', methods=['PUT'])
def api_update_question(id):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing JSON"}), 400

    q = MainExamQuestion.query.get_or_404(id)

    # map allowed fields
    for fld in ['question_text', 'choice_a', 'choice_b', 'choice_c', 'choice_d', 'subject', 'difficulty', 'correct_option']:
        if fld in data:
            # be careful: front-end uses question_text and correct_option
            setattr(q, fld, data[fld])

    db.session.commit()
    log_activity(f"Edited exam question ID: {id}", user="Administrator")
    return jsonify({"success": True})

def generate_reference_code():
    year = datetime.now().year
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"GRC-{year}-{random_part}"

@app.route('/admin/enrollees/import', methods=['POST'])
def import_enrollees():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename.endswith(('.csv', '.xlsx')):
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400

    try:
        # read file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(TextIOWrapper(file, encoding='utf-8'))
        else:
            df = pd.read_excel(file)

        enrollees_to_add = []

        for _, row in df.iterrows():
            name = row.get('Name')
            email = row.get('Email')
            if not name or not email:
                continue

            # Generate unique reference code
            reference_code = row.get('Reference Code')
            if pd.isna(reference_code) or str(reference_code).strip() == '':
                reference_code = f"GRC-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

            status = row.get('Status')
            if pd.isna(status) or str(status).strip() == '':
                status = 'not_started'

            registration_date = row.get('Date of Registration')
            if pd.isna(registration_date):
                registration_date = datetime.today().date()
            else:
                registration_date = pd.to_datetime(registration_date).date()

            exam_date = row.get('Exam Date')
            if pd.isna(exam_date):
                exam_date = None
            else:
                exam_date = pd.to_datetime(exam_date).date()

            enrollee = Enrollee(
                name=name,
                email=email,
                contact_number=row.get('Contact Number', None),
                school_strand=row.get('School/Strand', None),
                reference_code=reference_code,
                status=status,
                registration_date=registration_date,
                exam_date=exam_date
            )
            enrollees_to_add.append(enrollee)

        db.session.bulk_save_objects(enrollees_to_add)
        db.session.commit()

        return jsonify({'success': True, 'message': f'{len(enrollees_to_add)} enrollees imported successfully'})

    except Exception as e:
        db.session.rollback()
        # return full traceback for debugging
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

# -------------------------------------------------
# CACHE CONTROL
# -------------------------------------------------
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# -------------------------------------------------
# RUN APP
# -------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)


