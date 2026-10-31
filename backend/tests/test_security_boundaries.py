import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import Base, User, Teacher, Student, Course, Enrollment, GradeItem, ReportCard, ReportCardCourse, AIWarning
from routes.ai import check_student_grades


@pytest.mark.parametrize('secret', [None, '', 'change-me-before-production', 'short'])
def test_jwt_startup_rejects_unsafe_secret_without_mode(secret):
    result = auth_import(secret)
    assert result.returncode != 0
    assert 'JWT_SECRET_KEY' in result.stderr


def auth_import(secret, mode=None):
    env = os.environ.copy()
    for key in ('APP_ENV', 'ENVIRONMENT', 'JWT_SECRET_KEY'):
        env.pop(key, None)
    if secret is not None:
        env['JWT_SECRET_KEY'] = secret
    if mode:
        env['APP_ENV'] = mode
    # Ignore machine-local dotenv values; exercise only the supplied startup configuration.
    return subprocess.run(
        [sys.executable, '-c', 'import dotenv; dotenv.load_dotenv=lambda *a, **k: None; import auth'],
        env=env, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
    )


def test_jwt_startup_accepts_strong_secret():
    import secrets
    assert auth_import(secrets.token_urlsafe(48)).returncode == 0


@pytest.mark.parametrize('mode', ['local', 'test'])
def test_jwt_explicit_local_test_opt_in(mode):
    assert auth_import(None, mode).returncode == 0


def test_teacher_checker_is_course_scoped_and_preserves_stored_warnings():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            teachers = [Teacher(employee_number=f'ZZ-TEST-{i}', user=User(name=f'ZZ-TEST-{i}', email=f'zz-test-{i}@example.test', role='teacher', password_hash='hash')) for i in range(2)]
            student = Student(first_name='ZZ-TEST', last_name='Student', student_number='ZZ-TEST-SEC')
            courses = [Course(name=f'ZZ-TEST-Course-{i}', code=f'ZZ-TEST-{i}', teacher=teachers[i], term='1er Trimestre', school_year='2026-2027') for i in range(2)]
            report = ReportCard(student=student, term='1er Trimestre', school_year='2026-2027', overall_average=12, status='draft')
            db.add(report)
            for course in courses:
                db.add(Enrollment(student=student, course=course))
                db.add(GradeItem(course=course, title=course.name, category='Quiz', weight=1, max_score=20, term=course.term))
                db.add(ReportCardCourse(report_card=report, course=course, course_name=course.name, average=12, letter_grade='B'))
            db.flush()
            warning = AIWarning(report_card_id=report.id, warning_type='existing', message='Other teacher warning', severity='high')
            db.add(warning)
            db.commit()
            warning_id = warning.id
            warnings = check_student_grades(student.id, db, teachers[0].user)
            messages = ' '.join(w.message for w in warnings)
            assert courses[0].name in messages
            assert courses[1].name not in messages
            assert [w.id for w in db.scalars(select(AIWarning)).all()] == [warning_id]
    finally:
        engine.dispose()
