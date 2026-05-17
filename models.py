from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Enrollee(db.Model):
    __tablename__ = "enrollees"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique = True)
    contact_number = db.Column(db.String(20), nullable=True)
    school_strand = db.Column(db.String(255), nullable=True)

    reference_code = db.Column(db.String(50), nullable=False, unique=True)
    student_id = db.Column(db.String(50), nullable=True, unique=True)
    reference_expiration = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(20), default="not_started", nullable=False)
    registration_date = db.Column(db.Date, default=datetime.utcnow)
    exam_date = db.Column(db.Date, nullable=True)
    time_taken = db.Column(db.String(20), nullable=True)
    time_accomplished = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exam_results = db.relationship(
        "ExamResult",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy=True,
    )

    exam_attempts = db.relationship(
        "ExamAttempt",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "contact_number": self.contact_number,
            "school_strand": self.school_strand,
            "reference_code": self.reference_code,
            "student_id": self.student_id,
            "status": self.status or "not_started",
            "registration_date": self.registration_date.isoformat() if self.registration_date else None,
            "exam_date": self.exam_date.isoformat() if self.exam_date else None,
            "time_taken": self.time_taken,
            "time_accomplished": self.time_accomplished,
            "reference_expiration": self.reference_expiration.isoformat() if self.reference_expiration else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class ExamQuestion(db.Model):
    __tablename__ = "exam_questions"

    id = db.Column(db.Integer, primary_key=True)

    subject = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)

    question_text = db.Column(db.Text, nullable=False)
    question_image = db.Column(db.String(255), nullable=True)

    choice_a = db.Column(db.String(255), nullable=False)
    choice_b = db.Column(db.String(255), nullable=False)
    choice_c = db.Column(db.String(255), nullable=False)
    choice_d = db.Column(db.String(255), nullable=False)

    correct_option = db.Column(db.String(1), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    answers = db.relationship(
        "StudentAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "question_text": self.question_text,
            "question_image": self.question_image,
            "image_filename": self.question_image,
            "choice_a": self.choice_a,
            "choice_b": self.choice_b,
            "choice_c": self.choice_c,
            "choice_d": self.choice_d,
            "correct_option": self.correct_option,
            "date_added": self.date_added.strftime("%Y-%m-%d %H:%M") if self.date_added else None,
        }


class ExamResult(db.Model):
    __tablename__ = "exam_results"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("enrollees.id"), nullable=False)
    exam_type = db.Column(db.String(50), default="main", nullable=False)

    correct_answers = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)

    recommended_program = db.Column(db.String(255), nullable=True)
    match_percentage = db.Column(db.Integer, nullable=True)
    qualification_status = db.Column(db.String(50), nullable=True)

    status = db.Column(db.String(20), default="completed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    top_recommendations = db.Column(db.Text)

    student = db.relationship("Enrollee", back_populates="exam_results")

    answers = db.relationship(
        "StudentAnswer",
        back_populates="exam_result",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "exam_type": self.exam_type,
            "correct_answers": self.correct_answers,
            "total_questions": self.total_questions,
            "recommended_program": self.recommended_program,
            "match_percentage": self.match_percentage,
            "qualification_status": self.qualification_status,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class ExamAttempt(db.Model):
    __tablename__ = "exam_attempts"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("enrollees.id"), nullable=False)
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Enrollee", back_populates="exam_attempts")

    answers = db.relationship(
        "StudentAnswer",
        back_populates="exam_attempt",
        cascade="all, delete-orphan",
        lazy=True,
    )


class StudentAnswer(db.Model):
    __tablename__ = "student_answers"

    id = db.Column(db.Integer, primary_key=True)

    exam_result_id = db.Column(db.Integer, db.ForeignKey("exam_results.id"), nullable=True)
    exam_attempt_id = db.Column(db.Integer, db.ForeignKey("exam_attempts.id"), nullable=True)
    question_id = db.Column(db.Integer, db.ForeignKey("exam_questions.id"), nullable=False)

    selected_answer = db.Column(db.String(1), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exam_result = db.relationship("ExamResult", back_populates="answers")
    exam_attempt = db.relationship("ExamAttempt", back_populates="answers")
    question = db.relationship("ExamQuestion", back_populates="answers")


class ActivityLog(db.Model):
    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)

    action = db.Column(db.String(255), nullable=False)
    user = db.Column(db.String(100), default="System")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def record(action, user="System"):
        db.session.add(ActivityLog(action=action, user=user))
        db.session.commit()

    @staticmethod
    def log_activity(user, action):
        ActivityLog.record(action=action, user=user)
