from flask_sqlalchemy import SQLAlchemy
from datetime import datetime


db = SQLAlchemy()

class MainExamQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    choice_a = db.Column(db.Text, nullable=False)
    choice_b = db.Column(db.Text, nullable=False)
    choice_c = db.Column(db.Text, nullable=False)
    choice_d = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "question_text": self.question_text,
            "choice_a": self.choice_a,
            "choice_b": self.choice_b,
            "choice_c": self.choice_c,
            "choice_d": self.choice_d,
            "correct_option": self.correct_option,
            "date_added": self.date_added.isoformat() if self.date_added else None
        }

class ExamResult(db.Model):
    __tablename__ = 'exam_results'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('enrollees.id'), nullable=False)
    exam_type = db.Column(db.String(20), nullable=False)  # 'main' or 'aptitude'
    score = db.Column(db.Integer)
    total_questions = db.Column(db.Integer)
    correct_answers = db.Column(db.Integer)
    status = db.Column(db.String(20), default='in_progress')  
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    

    student_answers = db.relationship('StudentAnswer', backref='exam_result', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ExamResult {self.exam_type} - Student {self.student_id}>'

class Enrollee(db.Model):
    __tablename__ = 'enrollees'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    contact_number = db.Column(db.String(20), nullable=True)
    school_strand = db.Column(db.String(255), nullable=True)
    reference_code = db.Column(db.String(50), nullable=False, unique=True)
    status = db.Column(db.String(20), default='not_started', nullable=False)
    registration_date = db.Column(db.Date, default=db.func.current_date)
    exam_date = db.Column(db.Date, nullable=True)
    time_taken = db.Column(db.String(20), nullable=True)
    time_accomplished = db.Column(db.String(50), nullable=True)
    reference_expiration = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    def to_dict(self):
        return {
        'id': self.id,
        'name': self.name,
        'email': self.email,
        'reference_code': self.reference_code,
        'status': self.status or 'not_started',
        'time_taken': self.time_taken,
        'time_accomplished': self.time_accomplished,
        'registration_date': self.registration_date.isoformat() if self.registration_date else None,
        'exam_date': self.exam_date.isoformat() if self.exam_date else None,
        'reference_expiration': self.reference_expiration.isoformat() if self.reference_expiration else None,
        'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
    }
    
    def __repr__(self):
        return f'<Enrollee {self.name}>'
    
class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    __table_args__ = {'extend_existing': True}  

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user = db.Column(db.String(100), default="System")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    
    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "user": self.user,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def log_activity(user, action):
        new_log = ActivityLog(user=user, action=action)
        db.session.add(new_log)
        db.session.commit()


class ExamQuestion(db.Model):
    __tablename__ = 'exam_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_type = db.Column(db.String(20), nullable=False)  # 'main' or 'aptitude'
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
   
    student_answers = db.relationship('StudentAnswer', backref='question', lazy=True)
    
    def __repr__(self):
        return f'<ExamQuestion {self.id} - {self.exam_type}>'


class StudentAnswer(db.Model):
    __tablename__ = 'student_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey('exam_results.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('exam_questions.id'), nullable=False)
    selected_answer = db.Column(db.String(1))  # 'A', 'B', 'C', 'D', or NULL
    is_correct = db.Column(db.Boolean)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<StudentAnswer {self.id} - Question {self.question_id}>'