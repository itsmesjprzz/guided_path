import csv
from app import app, db       # import your existing Flask app instance
from models import MainExamQuestion

# Push app context
app.app_context().push()

csv_file = 'questions.csv'  # path to your CSV file

with open(csv_file, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        q = MainExamQuestion(
            subject=row['subject'],
            difficulty=row['difficulty'],
            question_text=row['question_text'],
            question_image=row.get('question_image', None),
            choice_a=row['choice_a'],
            choice_b=row['choice_b'],
            choice_c=row['choice_c'],
            choice_d=row['choice_d'],
            correct_option=row['correct_option']
        )
        db.session.add(q)
    db.session.commit()

print("✅ CSV imported into MainExamQuestion table")
